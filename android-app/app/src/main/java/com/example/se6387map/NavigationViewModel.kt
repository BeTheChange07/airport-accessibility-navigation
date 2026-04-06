package com.example.se6387map

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.android.gms.maps.model.LatLng
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

// --- Tunable constants ---
const val SIMULATION_STEP_INTERVAL_MS = 2000L
const val OFF_PATH_THRESHOLD_METERS = 15.0
const val OFF_PATH_TELEPORT_METERS = 25.0

enum class RestroomGender { ANY, MALE, FEMALE }

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
    // Zone of the user's current starting node ('public' or 'secure').
    // Used to keep off-path teleports and recalculations within the
    // same airside/landside partition as the user.
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
)

fun filteredAmenities(state: NavigationState): List<Amenity> = state.amenities.filter { a ->
    val chipOk = state.activeTypeFilters.isEmpty() || a.type in state.activeTypeFilters
    val dropdownOk = state.dropdownTypeFilter == null || a.type == state.dropdownTypeFilter
    val accessOk = !state.accessibilityMode ||
        a.has_accessible_unit == true ||
        a.wheelchairaccessible.equals("yes", ignoreCase = true)
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
    chipOk && dropdownOk && accessOk && genderOk
}

class NavigationViewModel : ViewModel() {

    private val _state = MutableStateFlow(NavigationState())
    val state: StateFlow<NavigationState> = _state

    private val api = NavigationApi.service
    private var simulationJob: Job? = null

    // ── Amenity types ──────────────────────────────────────────────

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

    fun loadAmenities() {
        viewModelScope.launch {
            try {
                val response = api.getAmenities()
                _state.value = _state.value.copy(amenities = response.amenities)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = "Failed to load amenities: ${e.message}")
            }
        }
    }

    // ── Selection + filter toggles ─────────────────────────────────

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
        // Reset gender sub-filter when the type changes (or is cleared)
        val resetGender = current.dropdownTypeFilter != type
        _state.value = current.copy(
            dropdownTypeFilter = type,
            restroomGenderFilter = if (resetGender) RestroomGender.ANY else current.restroomGenderFilter
        )
    }

    fun setRestroomGender(gender: RestroomGender) {
        _state.value = _state.value.copy(restroomGenderFilter = gender)
    }

    /**
     * Route to the nearest amenity matching the current dropdown filter context
     * (type + gender + accessibility). Picks closest by haversine to user location.
     */
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

    fun routeToSpecificAmenity(amenity: Amenity) {
        val currentLocation = _state.value.userLocation ?: return
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null)
            try {
                val nearest = api.getNearestNode(
                    currentLocation.latitude, currentLocation.longitude, _state.value.currentZone
                )
                _state.value = _state.value.copy(currentZone = nearest.zone)
                // /api/amenities now returns the linked nav_node's lat/lng, so
                // amenity.nodeid is authoritative and lives in the same frame as
                // the marker we just drew.
                val response = api.getRoute(nearest.node_id, amenity.nodeid)
                // Preserve the chosen amenity's name as the destination label
                applyRouteResponse(response.copy(destination_name = amenity.name))
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = "Failed to route to ${amenity.name}: ${e.message}"
                )
            }
        }
    }

    // ── Route to specific amenity type ─────────────────────────────

    fun routeToAmenity(amenityType: String) {
        val currentLocation = _state.value.userLocation ?: return
        viewModelScope.launch {
            _state.value = _state.value.copy(
                isLoading = true, error = null, selectedAmenityType = amenityType
            )
            try {
                // First find the nearest node to simulated position
                val nearest = api.getNearestNode(currentLocation.latitude, currentLocation.longitude)
                // Remember this node's zone so off-path recalcs stay airside/landside-correct
                _state.value = _state.value.copy(currentZone = nearest.zone)
                // Then route to nearest amenity of that type
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

    // ── Fetch a direct node-to-node route ──────────────────────────

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
            userLocation = points.firstOrNull() ?: _state.value.userLocation
        )
    }

    // ── Simulation engine ──────────────────────────────────────────

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
                    // Arrived
                    _state.value = _state.value.copy(
                        currentInstruction = "You have arrived at ${_state.value.destinationName}!",
                        isSimulating = false,
                        isNavigating = false,
                        distanceToNextMeters = 0.0
                    )
                    return@launch
                }

                delay(SIMULATION_STEP_INTERVAL_MS)

                // Check if simulation was stopped externally
                if (!_state.value.isSimulating) return@launch
            }
        }
    }

    fun stopSimulation() {
        simulationJob?.cancel()
        simulationJob = null
        _state.value = _state.value.copy(isSimulating = false)
    }

    // ── Off-path detection & recalculation ─────────────────────────

    fun goOffPath() {
        val current = _state.value.userLocation ?: return
        val destinationId = _state.value.destinationNodeId ?: return
        // Zone of the user's current starting point. Off-path teleports
        // MUST stay within this zone — a secure-side passenger cannot
        // legally cross TSA to a public-side node and vice versa.
        val zone = _state.value.currentZone

        // Teleport ~25 meters roughly north-east of current position
        // 1 degree lat ≈ 111,000 m, so 25m ≈ 0.000225 degrees
        val offsetLat = OFF_PATH_TELEPORT_METERS / 111000.0
        val offsetLng = OFF_PATH_TELEPORT_METERS / (111000.0 * Math.cos(Math.toRadians(current.latitude)))
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
                // Constrain the snap-to-nearest to the user's current zone so
                // we never teleport across the secure/public boundary.
                val nearest = api.getNearestNode(from.latitude, from.longitude, zone)
                _state.value = _state.value.copy(currentZone = nearest.zone)
                val response = api.getRoute(nearest.node_id, destinationNodeId)
                applyRouteResponse(response)
                _state.value = _state.value.copy(isRecalculating = false)
                // Auto-resume simulation on the new route
                startSimulation()
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isRecalculating = false,
                    error = "Recalculation failed: ${e.message}"
                )
            }
        }
    }

    /**
     * Check if the given position is off the current route polyline.
     * Returns true if minimum distance to any segment exceeds the threshold.
     */
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

    // ── Location update (used by real GPS if ever connected) ───────

    fun updateUserLocation(location: LatLng) {
        // Don't let real GPS overwrite the simulated position while a
        // simulation is running — otherwise the camera jumps to the
        // device's physical location every fix and snaps back on the
        // next simulated step.
        if (_state.value.isSimulating) return
        _state.value = _state.value.copy(userLocation = location)

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
                val nearest = api.getNearestNode(lat, lng)
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
            userLocation = prev.userLocation
        )
    }

    fun setMockLocation() {
        _state.value = _state.value.copy(
            userLocation = LatLng(32.89768836069466, -97.04474161852207)
        )
    }

    // ── Geometry helpers ───────────────────────────────────────────

    private fun distanceBetween(a: LatLng, b: LatLng): Double {
        val dlat = a.latitude - b.latitude
        val dlng = a.longitude - b.longitude
        return Math.sqrt(dlat * dlat + dlng * dlng)
    }

    internal fun pointToSegmentDistanceMeters(p: LatLng, a: LatLng, b: LatLng): Double {
        // Project point p onto segment a-b, compute haversine distance to closest point
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
