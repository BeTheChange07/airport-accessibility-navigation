package com.example.se6387map

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.android.gms.maps.model.LatLng
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

// Tunable constants
const val SIMULATION_STEP_INTERVAL_MS = 2000L
const val OFF_PATH_THRESHOLD_METERS = 15.0
// Random 5–10m nudge to force a recalc without visibly teleporting.
const val OFF_PATH_NUDGE_MIN_METERS = 5.0
const val OFF_PATH_NUDGE_MAX_METERS = 10.0

// Amenity polling cadence. Faster while the user is navigating so the
// "destination just filled up / closed" prompt is demo-responsive.
const val AMENITY_POLL_INTERVAL_IDLE_MS = 15_000L
const val AMENITY_POLL_INTERVAL_NAV_MS = 5_000L

// Statuses an admin can set that mean "don't route here."
internal val AMENITY_UNROUTABLE_STATUSES = setOf("closed", "maintenance", "out_of_service")

enum class RestroomGender { ANY, MALE, FEMALE }

/** Why the ViewModel wants the user to reroute mid-navigation. */
data class ReroutePrompt(
    val reason: String,             // "full" or "closed"
    val amenityType: String,
    val originalDestinationName: String,
)

data class NavigationState(
    val isLoading: Boolean = false,
    val routePoints: List<LatLng> = emptyList(),
    val waypoints: List<Waypoint> = emptyList(),
    val currentInstruction: String = "Select a destination",
    val currentWaypointIndex: Int = 0,
    val userLocation: LatLng? = null,
    val error: String? = null,
    val isNavigating: Boolean = false,
    // Amenity selection
    val amenityTypes: List<String> = emptyList(),
    val selectedAmenityType: String? = null,
    val destinationName: String? = null,
    // Simulation
    val isSimulating: Boolean = false,
    val currentBearing: Float = 0f,
    val distanceToNextMeters: Double = 0.0,
    val cardinalDirection: String = "",
    // Off-path
    val isRecalculating: Boolean = false,
    val destinationNodeId: Int? = null,
    // User's current zone ('public' or 'secure').
    val currentZone: String? = null,
    // Amenities + filters
    val amenities: List<Amenity> = emptyList(),
    val selectedAmenity: Amenity? = null,
    val accessibilityMode: Boolean = false,
    val activeTypeFilters: Set<String> = emptySet(),
    val showAmenityList: Boolean = false,
    // Single-type focus from the dropdown (separate from chip multi-select)
    val dropdownTypeFilter: String? = null,
    val restroomGenderFilter: RestroomGender = RestroomGender.ANY,
    // Cross-zone amenity parked here until the user confirms or cancels.
    val pendingCrossZoneAmenity: Amenity? = null,
    // Iteration 2:
    // Track the amenity-level id of the current destination so polling can
    // spot mid-route status / occupancy changes.
    val destinationAmenityId: Int? = null,
    val lastKnownDestinationStatus: String? = null,
    val lastKnownDestinationOccupancy: String? = null,
    // Parked here until the user confirms or declines the corresponding prompt.
    val pendingOccupancyWarning: Amenity? = null,   // route-start warning (UC5 specific-pin)
    val pendingReroutePrompt: ReroutePrompt? = null, // mid-route full / closed (UC5 + UC7)
)

fun filteredAmenities(state: NavigationState): List<Amenity> = state.amenities.filter { a ->
    val chipOk = state.activeTypeFilters.isEmpty() || a.type in state.activeTypeFilters
    val dropdownOk = state.dropdownTypeFilter == null || a.type == state.dropdownTypeFilter
    val accessOk = !state.accessibilityMode ||
        a.has_accessible_unit == true ||
        a.wheelchairaccessible.equals("yes", ignoreCase = true)
    // Hide amenities until the user picks a starting zone.
    val zoneOk = state.currentZone != null && a.zone == state.currentZone
    val genderOk = if (state.dropdownTypeFilter == "restroom" &&
        state.restroomGenderFilter != RestroomGender.ANY
    ) {
        // Check Female first — "Female Bathroom" contains the substring "male".
        val isFemale = a.name.startsWith("Female", ignoreCase = true)
        val isMale = !isFemale && a.name.contains(Regex("(?i)\\bmale\\b"))
        when (state.restroomGenderFilter) {
            RestroomGender.FEMALE -> isFemale
            RestroomGender.MALE -> isMale
            RestroomGender.ANY -> true
        }
    } else true
    chipOk && dropdownOk && accessOk && zoneOk && genderOk
}

class NavigationViewModel : ViewModel() {

    private val _state = MutableStateFlow(NavigationState())
    val state: StateFlow<NavigationState> = _state

    private val api = NavigationApi.service
    private var simulationJob: Job? = null
    private var pollingJob: Job? = null

    fun loadAmenityTypes() {
        viewModelScope.launch {
            try {
                val response = api.getAmenityTypes()
                _state.value = _state.value.copy(amenityTypes = response.amenity_types)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = "Failed to load amenity types: ${e.message}")
            }
        }
    }

    /**
     * Fetch amenities and start the background polling loop if it isn't
     * already running. Called from MainActivity on app start; safe to call
     * repeatedly. Starts polling lazily (rather than in `init`) so unit
     * tests that construct the ViewModel directly don't need a Main
     * dispatcher to be available.
     */
    fun loadAmenities() {
        startAmenityPollingIfNeeded()
    }

    private fun startAmenityPollingIfNeeded() {
        if (pollingJob?.isActive == true) return
        pollingJob = viewModelScope.launch {
            while (true) {
                try {
                    val response = api.getAmenities()
                    val sample = response.amenities.firstOrNull { it.type == "restroom" }
                    Log.d(
                        "AmenityPoll",
                        "got ${response.amenities.size} amenities " +
                            "(sample restroom: ${sample?.name} status=${sample?.status} " +
                            "occ=${sample?.occupancy} crowd=${sample?.crowdlevel})"
                    )
                    onAmenitiesRefreshed(response.amenities)
                } catch (e: Exception) {
                    Log.w("AmenityPoll", "fetch failed: ${e.message}")
                }
                val interval = if (_state.value.isNavigating)
                    AMENITY_POLL_INTERVAL_NAV_MS else AMENITY_POLL_INTERVAL_IDLE_MS
                delay(interval)
            }
        }
    }

    /**
     * Handle a fresh amenities payload. In addition to updating the map,
     * watch for status / occupancy transitions on the active destination
     * so we can prompt the user to reroute.
     */
    private fun onAmenitiesRefreshed(fresh: List<Amenity>) {
        val prev = _state.value
        val destId = prev.destinationAmenityId
        val destAmenity = if (destId != null) fresh.firstOrNull { it.id == destId } else null

        var newPrompt: ReroutePrompt? = prev.pendingReroutePrompt
        // Only fire a new prompt while actively navigating and if we're not
        // already prompting. Once the user accepts or declines, we reset.
        if (destAmenity != null && prev.isNavigating && newPrompt == null) {
            val nowFull = destAmenity.occupancy == "full"
            val wasFull = prev.lastKnownDestinationOccupancy == "full"
            val nowClosed = destAmenity.status in AMENITY_UNROUTABLE_STATUSES
            val wasClosed = prev.lastKnownDestinationStatus in AMENITY_UNROUTABLE_STATUSES
            newPrompt = when {
                nowFull && !wasFull -> ReroutePrompt(
                    reason = "full",
                    amenityType = destAmenity.type,
                    originalDestinationName = destAmenity.name
                )
                nowClosed && !wasClosed -> ReroutePrompt(
                    reason = "closed",
                    amenityType = destAmenity.type,
                    originalDestinationName = destAmenity.name
                )
                else -> null
            }
        }

        _state.value = prev.copy(
            amenities = fresh,
            lastKnownDestinationStatus = destAmenity?.status ?: prev.lastKnownDestinationStatus,
            lastKnownDestinationOccupancy = destAmenity?.occupancy ?: prev.lastKnownDestinationOccupancy,
            pendingReroutePrompt = newPrompt
        )
    }

    fun selectAmenity(amenity: Amenity) {
        _state.value = _state.value.copy(selectedAmenity = amenity)
    }

    fun clearSelectedAmenity() {
        _state.value = _state.value.copy(selectedAmenity = null)
    }

    fun toggleAccessibilityMode() {
        _state.value = _state.value.copy(accessibilityMode = !_state.value.accessibilityMode)
    }

    fun setTypeFilter(type: String, enabled: Boolean) {
        val updated = _state.value.activeTypeFilters.toMutableSet().apply {
            if (enabled) add(type) else remove(type)
        }
        _state.value = _state.value.copy(activeTypeFilters = updated)
    }

    fun toggleAmenityList() {
        _state.value = _state.value.copy(showAmenityList = !_state.value.showAmenityList)
    }

    fun setDropdownTypeFilter(type: String?) {
        val current = _state.value
        // Reset gender sub-filter when the type changes.
        val resetGender = current.dropdownTypeFilter != type
        _state.value = current.copy(
            dropdownTypeFilter = type,
            restroomGenderFilter = if (resetGender) RestroomGender.ANY else current.restroomGenderFilter
        )
    }

    fun setRestroomGender(gender: RestroomGender) {
        _state.value = _state.value.copy(restroomGenderFilter = gender)
    }

    /** Route to the closest amenity matching current filters by haversine distance. */
    fun routeToNearestFilteredRestroom() {
        val state = _state.value
        val user = state.userLocation ?: return
        val candidates = filteredAmenities(state)
        if (candidates.isEmpty()) {
            _state.value = state.copy(error = "No matching restrooms found.")
            return
        }
        val closest = candidates.minByOrNull {
            haversineMeters(user, LatLng(it.latitude, it.longitude))
        } ?: return
        routeToSpecificAmenity(closest)
    }

    /** Test-only synchronous seed: place the user at [location] in [zone]. */
    internal fun seedStartForTest(location: LatLng, zone: String) {
        _state.value = _state.value.copy(userLocation = location, currentZone = zone)
    }

    fun routeToSpecificAmenity(amenity: Amenity) {
        val currentLocation = _state.value.userLocation ?: return
        val zone = _state.value.currentZone
        // Defense in depth: filter normally hides this, but double-check.
        if (zone != null && amenity.zone != null && amenity.zone != zone) {
            _state.value = _state.value.copy(pendingCrossZoneAmenity = amenity)
            return
        }
        // UC5: warn before routing to a high-occupancy or full restroom.
        // The backend's /api/route doesn't filter by occupancy (it obeys
        // the user's explicit choice), so the confirmation lives here.
        if (amenity.occupancy == "high" || amenity.occupancy == "full") {
            _state.value = _state.value.copy(pendingOccupancyWarning = amenity)
            return
        }
        executeRouteToAmenity(amenity, currentLocation)
    }

    /** User acknowledged the high/full warning and wants to route anyway. */
    fun confirmOccupancyWarning() {
        val amenity = _state.value.pendingOccupancyWarning ?: return
        val loc = _state.value.userLocation
        _state.value = _state.value.copy(pendingOccupancyWarning = null)
        if (loc != null) executeRouteToAmenity(amenity, loc)
    }

    fun dismissOccupancyWarning() {
        _state.value = _state.value.copy(pendingOccupancyWarning = null)
    }

    /** User accepted the mid-route "destination filled up / closed" prompt. */
    fun acceptReroutePrompt() {
        val prompt = _state.value.pendingReroutePrompt ?: return
        // Clear both the prompt and the previous destination tracking so the
        // new call seeds cleanly.
        _state.value = _state.value.copy(
            pendingReroutePrompt = null,
            destinationAmenityId = null,
            lastKnownDestinationStatus = null,
            lastKnownDestinationOccupancy = null,
        )
        // Backend's /api/route-to-amenity filter now skips full/closed, so
        // this returns the next-nearest usable one automatically.
        routeToAmenity(prompt.amenityType)
    }

    fun declineReroutePrompt() {
        _state.value = _state.value.copy(pendingReroutePrompt = null)
    }

    private fun executeRouteToAmenity(amenity: Amenity, currentLocation: LatLng) {
        viewModelScope.launch {
            _state.value = _state.value.copy(
                isLoading = true,
                error = null,
                // Seed destination tracking so onAmenitiesRefreshed can catch
                // status/occupancy changes after navigation starts.
                destinationAmenityId = amenity.id,
                lastKnownDestinationStatus = amenity.status,
                lastKnownDestinationOccupancy = amenity.occupancy,
            )
            try {
                val nearest = api.getNearestNode(
                    currentLocation.latitude, currentLocation.longitude, _state.value.currentZone
                )
                _state.value = _state.value.copy(currentZone = nearest.zone)
                val response = api.getRoute(nearest.node_id, amenity.nodeid)
                applyRouteResponse(response.copy(destination_name = amenity.name))
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = "Failed to route to ${amenity.name}: ${e.message}"
                )
            }
        }
    }

    /** User cancelled the cross-zone confirm dialog. */
    fun cancelCrossZoneRoute() {
        _state.value = _state.value.copy(pendingCrossZoneAmenity = null)
    }

    /** User confirmed the cross-zone route; pgRouting walks through the TSA edges. */
    fun confirmCrossZoneRoute() {
        val amenity = _state.value.pendingCrossZoneAmenity ?: return
        val currentLocation = _state.value.userLocation
        _state.value = _state.value.copy(pendingCrossZoneAmenity = null)
        if (currentLocation == null) return
        executeRouteToAmenity(amenity, currentLocation)
    }

    fun routeToAmenity(amenityType: String) {
        val currentLocation = _state.value.userLocation ?: return
        viewModelScope.launch {
            _state.value = _state.value.copy(
                isLoading = true, error = null, selectedAmenityType = amenityType
            )
            try {
                // Constrain nearest-node lookup to the user's current zone.
                val nearest = api.getNearestNode(
                    currentLocation.latitude, currentLocation.longitude, _state.value.currentZone
                )
                _state.value = _state.value.copy(currentZone = nearest.zone)
                val accessible = _state.value.accessibilityMode
                val response = api.getRouteToAmenity(
                    nearest.node_id, amenityType, if (accessible) true else null
                )
                applyRouteResponse(response)
            } catch (e: retrofit2.HttpException) {
                val body = try { e.response()?.errorBody()?.string() } catch (_: Exception) { null }
                val msg = body ?: e.message ?: "Request failed"
                val friendly = if (e.code() == 404 && _state.value.accessibilityMode) {
                    "No accessible $amenityType found near you. Try turning off accessibility mode."
                } else msg
                _state.value = _state.value.copy(isLoading = false, error = friendly)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = "Failed to route to amenity: ${e.message}"
                )
            }
        }
    }

    fun fetchRoute(fromNode: Int, toNode: Int) {
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null)
            try {
                val response = api.getRoute(fromNode, toNode)
                applyRouteResponse(response)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = "Failed to get route: ${e.message}"
                )
            }
        }
    }

    private fun applyRouteResponse(response: RouteResponse) {
        // If the user was simulating the previous route, stop that coroutine
        // BEFORE we swap in the new waypoints. startSimulation captures the
        // waypoint list at launch time, so without this the old sim would
        // keep walking the dead path even though the polyline has flipped.
        val wasSimulating = _state.value.isSimulating
        if (wasSimulating) stopSimulation()

        val points = response.waypoints.map { LatLng(it.latitude, it.longitude) }
        val firstWp = response.waypoints.firstOrNull()
        _state.value = _state.value.copy(
            isLoading = false,
            routePoints = points,
            waypoints = response.waypoints,
            currentInstruction = firstWp?.instruction ?: "Start walking",
            currentWaypointIndex = 0,
            isNavigating = true,
            destinationNodeId = response.to_node,
            destinationName = response.destination_name
                ?: response.waypoints.lastOrNull()?.label?.ifEmpty { null }
                ?: "Destination",
            currentBearing = firstWp?.bearing_to_next?.toFloat() ?: 0f,
            cardinalDirection = firstWp?.cardinal_direction ?: "",
            distanceToNextMeters = firstWp?.distance_meters ?: 0.0,
            userLocation = points.firstOrNull() ?: _state.value.userLocation,
            // Capture destination metadata when /api/route-to-amenity provided it,
            // otherwise keep whatever executeRouteToAmenity seeded.
            destinationAmenityId = response.destination_amenity_id
                ?: _state.value.destinationAmenityId,
            lastKnownDestinationStatus = response.destination_status
                ?: _state.value.lastKnownDestinationStatus,
            lastKnownDestinationOccupancy = response.destination_occupancy
                ?: _state.value.lastKnownDestinationOccupancy,
            // A fresh route clears any previous mid-route prompt.
            pendingReroutePrompt = null,
        )

        // Resume simulation on the new waypoints.
        if (wasSimulating) startSimulation()
    }

    fun startSimulation() {
        if (_state.value.waypoints.isEmpty()) return
        stopSimulation()

        _state.value = _state.value.copy(
            isSimulating = true,
            currentWaypointIndex = 0,
            userLocation = LatLng(
                _state.value.waypoints[0].latitude,
                _state.value.waypoints[0].longitude
            )
        )

        simulationJob = viewModelScope.launch {
            val waypoints = _state.value.waypoints
            for (i in waypoints.indices) {
                val wp = waypoints[i]
                _state.value = _state.value.copy(
                    currentWaypointIndex = i,
                    userLocation = LatLng(wp.latitude, wp.longitude),
                    currentInstruction = wp.instruction,
                    currentBearing = wp.bearing_to_next?.toFloat() ?: _state.value.currentBearing,
                    cardinalDirection = wp.cardinal_direction ?: _state.value.cardinalDirection,
                    distanceToNextMeters = wp.distance_meters ?: 0.0
                )

                if (i == waypoints.size - 1) {
                    _state.value = _state.value.copy(
                        currentInstruction = "You have arrived at ${_state.value.destinationName}!",
                        isSimulating = false,
                        isNavigating = false,
                        distanceToNextMeters = 0.0
                    )
                    return@launch
                }

                delay(SIMULATION_STEP_INTERVAL_MS)

                if (!_state.value.isSimulating) return@launch
            }
        }
    }

    fun stopSimulation() {
        simulationJob?.cancel()
        simulationJob = null
        _state.value = _state.value.copy(isSimulating = false)
    }

    fun goOffPath() {
        val current = _state.value.userLocation ?: return
        val destinationId = _state.value.destinationNodeId ?: return
        // Off-path teleports must stay in the user's current zone.
        val zone = _state.value.currentZone

        // Random bearing, 5–10m nudge to force a recalc.
        val angle = Math.random() * 2 * Math.PI
        val meters = OFF_PATH_NUDGE_MIN_METERS +
            Math.random() * (OFF_PATH_NUDGE_MAX_METERS - OFF_PATH_NUDGE_MIN_METERS)
        val offsetLat = (meters * Math.sin(angle)) / 111000.0
        val offsetLng = (meters * Math.cos(angle)) /
            (111000.0 * Math.cos(Math.toRadians(current.latitude)))
        val offPathLocation = LatLng(current.latitude + offsetLat, current.longitude + offsetLng)

        stopSimulation()
        _state.value = _state.value.copy(
            userLocation = offPathLocation,
            isRecalculating = true,
            currentInstruction = "Recalculating..."
        )

        recalculateRoute(offPathLocation, destinationId, zone)
    }

    private fun recalculateRoute(from: LatLng, destinationNodeId: Int, zone: String?) {
        viewModelScope.launch {
            try {
                // Stay in the user's zone when snapping to nearest.
                val nearest = api.getNearestNode(from.latitude, from.longitude, zone)
                _state.value = _state.value.copy(currentZone = nearest.zone)
                val response = api.getRoute(nearest.node_id, destinationNodeId)
                applyRouteResponse(response)
                _state.value = _state.value.copy(isRecalculating = false)
                startSimulation()
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isRecalculating = false,
                    error = "Recalculation failed: ${e.message}"
                )
            }
        }
    }

    /** True if [position] is more than the threshold away from the route. */
    fun isOffPath(position: LatLng): Boolean {
        val points = _state.value.routePoints
        if (points.size < 2) return false

        var minDist = Double.MAX_VALUE
        for (i in 0 until points.size - 1) {
            val dist = pointToSegmentDistanceMeters(position, points[i], points[i + 1])
            if (dist < minDist) minDist = dist
        }
        return minDist > OFF_PATH_THRESHOLD_METERS
    }

    fun updateUserLocation(location: LatLng) {
        val s = _state.value
        // Don't let real GPS overwrite a simulated or mock-start position.
        if (s.isSimulating || s.currentZone != null) return
        _state.value = s.copy(userLocation = location)

        if (_state.value.isNavigating && !_state.value.isSimulating && _state.value.waypoints.isNotEmpty()) {
            val currentIndex = _state.value.currentWaypointIndex
            if (currentIndex < _state.value.waypoints.size) {
                val targetWaypoint = _state.value.waypoints[currentIndex]
                val targetLatLng = LatLng(targetWaypoint.latitude, targetWaypoint.longitude)
                val distance = distanceBetween(location, targetLatLng)

                if (distance < 0.00005) {
                    val nextIndex = currentIndex + 1
                    if (nextIndex < _state.value.waypoints.size) {
                        val nextWp = _state.value.waypoints[nextIndex]
                        _state.value = _state.value.copy(
                            currentWaypointIndex = nextIndex,
                            currentInstruction = nextWp.instruction,
                            currentBearing = nextWp.bearing_to_next?.toFloat() ?: _state.value.currentBearing,
                            cardinalDirection = nextWp.cardinal_direction ?: "",
                            distanceToNextMeters = nextWp.distance_meters ?: 0.0
                        )
                    } else {
                        _state.value = _state.value.copy(
                            currentInstruction = "You have arrived!",
                            isNavigating = false
                        )
                    }
                }
            }
        }
    }

    fun findNearestAndRoute(lat: Double, lng: Double, destinationNode: Int) {
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null)
            try {
                val nearest = api.getNearestNode(lat, lng, _state.value.currentZone)
                _state.value = _state.value.copy(currentZone = nearest.zone)
                fetchRoute(nearest.node_id, destinationNode)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = "Failed to find nearest node: ${e.message}"
                )
            }
        }
    }

    fun stopNavigation() {
        stopSimulation()
        val prev = _state.value
        _state.value = NavigationState(
            amenityTypes = prev.amenityTypes,
            amenities = prev.amenities,
            accessibilityMode = prev.accessibilityMode,
            activeTypeFilters = prev.activeTypeFilters,
            userLocation = prev.userLocation,
            // Keep the zone so the amenity filter stays in place.
            currentZone = prev.currentZone
        )
    }

    /**
     * Reset state and drop the user at a random nav node in the requested
     * zone ('secure' or 'public'). Used by the on-screen test buttons.
     */
    fun setMockStart(zone: String) {
        stopSimulation()
        viewModelScope.launch {
            try {
                val node = api.getRandomNode(zone)
                val prev = _state.value
                _state.value = NavigationState(
                    amenityTypes = prev.amenityTypes,
                    amenities = prev.amenities,
                    accessibilityMode = prev.accessibilityMode,
                    activeTypeFilters = prev.activeTypeFilters,
                    dropdownTypeFilter = prev.dropdownTypeFilter,
                    restroomGenderFilter = prev.restroomGenderFilter,
                    userLocation = LatLng(node.latitude, node.longitude),
                    currentZone = node.zone,
                    currentInstruction = "Ready — pick a destination",
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    error = "Failed to get random $zone start: ${e.message}"
                )
            }
        }
    }

    private fun distanceBetween(a: LatLng, b: LatLng): Double {
        val dlat = a.latitude - b.latitude
        val dlng = a.longitude - b.longitude
        return Math.sqrt(dlat * dlat + dlng * dlng)
    }

    internal fun pointToSegmentDistanceMeters(p: LatLng, a: LatLng, b: LatLng): Double {
        // Project p onto segment a-b, then haversine to the closest point.
        val dx = b.longitude - a.longitude
        val dy = b.latitude - a.latitude
        if (dx == 0.0 && dy == 0.0) return haversineMeters(p, a)

        val t = ((p.longitude - a.longitude) * dx + (p.latitude - a.latitude) * dy) / (dx * dx + dy * dy)
        val clamped = t.coerceIn(0.0, 1.0)
        val closest = LatLng(a.latitude + clamped * dy, a.longitude + clamped * dx)
        return haversineMeters(p, closest)
    }

    private fun haversineMeters(a: LatLng, b: LatLng): Double {
        val R = 6371000.0
        val phi1 = Math.toRadians(a.latitude)
        val phi2 = Math.toRadians(b.latitude)
        val dphi = Math.toRadians(b.latitude - a.latitude)
        val dlambda = Math.toRadians(b.longitude - a.longitude)
        val sinHalf = Math.sin(dphi / 2)
        val sinHalfLng = Math.sin(dlambda / 2)
        val av = sinHalf * sinHalf + Math.cos(phi1) * Math.cos(phi2) * sinHalfLng * sinHalfLng
        return R * 2 * Math.atan2(Math.sqrt(av), Math.sqrt(1 - av))
    }
}
