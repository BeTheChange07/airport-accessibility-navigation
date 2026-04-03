package com.example.se6387map

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.android.gms.maps.model.LatLng
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

data class NavigationState(
    val isLoading: Boolean = false,
    val routePoints: List<LatLng> = emptyList(),
    val waypoints: List<Waypoint> = emptyList(),
    val currentInstruction: String = "Select a destination",
    val currentWaypointIndex: Int = 0,
    val userLocation: LatLng? = null,
    val error: String? = null,
    val isNavigating: Boolean = false
)

class NavigationViewModel : ViewModel() {

    private val _state = MutableStateFlow(NavigationState())
    val state: StateFlow<NavigationState> = _state

    private val api = NavigationApi.service

    fun fetchRoute(fromNode: Int, toNode: Int) {
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null)
            try {
                val response = api.getRoute(fromNode, toNode)
                val points = response.waypoints.map {
                    LatLng(it.latitude, it.longitude)
                }
                _state.value = _state.value.copy(
                    isLoading = false,
                    routePoints = points,
                    waypoints = response.waypoints,
                    currentInstruction = response.waypoints.firstOrNull()?.instruction ?: "Start walking",
                    currentWaypointIndex = 0,
                    isNavigating = true
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = "Failed to get route: ${e.message}"
                )
            }
        }
    }

    fun updateUserLocation(location: LatLng) {
        _state.value = _state.value.copy(userLocation = location)

        // If navigating, check if user is near the next waypoint
        if (_state.value.isNavigating && _state.value.waypoints.isNotEmpty()) {
            val currentIndex = _state.value.currentWaypointIndex
            if (currentIndex < _state.value.waypoints.size) {
                val targetWaypoint = _state.value.waypoints[currentIndex]
                val targetLatLng = LatLng(targetWaypoint.latitude, targetWaypoint.longitude)

                val distance = distanceBetween(location, targetLatLng)

                // If within ~5 meters of the next waypoint, advance
                if (distance < 0.00005) { // roughly 5 meters in degrees
                    val nextIndex = currentIndex + 1
                    if (nextIndex < _state.value.waypoints.size) {
                        _state.value = _state.value.copy(
                            currentWaypointIndex = nextIndex,
                            currentInstruction = _state.value.waypoints[nextIndex].instruction
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
                // Find nearest node to user's GPS position
                val nearest = api.getNearestNode(lat, lng)
                // Then get route from that node to destination
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
        _state.value = NavigationState()
    }

    private fun distanceBetween(a: LatLng, b: LatLng): Double {
        val dlat = a.latitude - b.latitude
        val dlng = a.longitude - b.longitude
        return Math.sqrt(dlat * dlat + dlng * dlng)
    }

    fun setMockLocation() {
        _state.value = _state.value.copy(
            userLocation = LatLng(32.89768836069466, -97.04474161852207)
        )
    }


}
