package com.example.se6387map

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.background
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.app.ActivityCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import com.google.android.gms.location.*
import com.google.android.gms.maps.CameraUpdateFactory
import com.google.android.gms.maps.model.BitmapDescriptorFactory
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.maps.android.compose.*

class MainActivity : ComponentActivity() {

    private lateinit var fusedLocationClient: FusedLocationProviderClient
    private var locationCallback: LocationCallback? = null
    internal var latestViewModel: NavigationViewModel? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this)

        val locationPermissionRequest = registerForActivityResult(
            ActivityResultContracts.RequestMultiplePermissions()
        ) { permissions ->
            if (permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true) {
                startLocationUpdates()
            }
        }

        setContent {
            MaterialTheme {
                val viewModel: NavigationViewModel = viewModel()
                val authViewModel: AuthViewModel = viewModel()
                val reportsViewModel: ReportsViewModel = viewModel()
                latestViewModel = viewModel

                LaunchedEffect(Unit) {
                    if (ActivityCompat.checkSelfPermission(
                            this@MainActivity,
                            Manifest.permission.ACCESS_FINE_LOCATION
                        ) == PackageManager.PERMISSION_GRANTED
                    ) {
                        startLocationUpdates()
                    } else {
                        locationPermissionRequest.launch(
                            arrayOf(
                                Manifest.permission.ACCESS_FINE_LOCATION,
                                Manifest.permission.ACCESS_COARSE_LOCATION
                            )
                        )
                    }

                    viewModel.loadAmenityTypes()
                    viewModel.loadAmenities()
                }

                NavigationScreen(
                    viewModel = viewModel,
                    authViewModel = authViewModel,
                    reportsViewModel = reportsViewModel,
                )
            }
        }
    }

    private fun startLocationUpdates() {
        val locationRequest = LocationRequest.Builder(
            Priority.PRIORITY_HIGH_ACCURACY, 2000L
        ).setMinUpdateIntervalMillis(1000L).build()

        locationCallback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                result.lastLocation?.let {
                    latestViewModel?.updateUserLocation(LatLng(it.latitude, it.longitude))
                }
            }
        }

        if (ActivityCompat.checkSelfPermission(
                this, Manifest.permission.ACCESS_FINE_LOCATION
            ) == PackageManager.PERMISSION_GRANTED
        ) {
            fusedLocationClient.requestLocationUpdates(
                locationRequest,
                locationCallback!!,
                Looper.getMainLooper()
            )
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        locationCallback?.let {
            fusedLocationClient.removeLocationUpdates(it)
        }
    }
}

@Composable
fun NavigationScreen(
    viewModel: NavigationViewModel,
    authViewModel: AuthViewModel,
    reportsViewModel: ReportsViewModel,
) {
    val state by viewModel.state.collectAsState()
    val authState by authViewModel.state.collectAsState()
    var showAccountSheet by remember { mutableStateOf(false) }
    // Reports sheet state. When non-null with prefilled = an Amenity, the
    // form is pre-locked to that amenity (entry point: amenity detail).
    // When non-null with prefilled = null, the user came from the Account
    // sheet's "My reports" button.
    var showReportsSheet by remember { mutableStateOf(false) }
    var reportPrefillAmenity by remember { mutableStateOf<Amenity?>(null) }

    val terminalD = LatLng(32.8980, -97.0435)
    val cameraPositionState = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(terminalD, 18f)
    }

    // Follow simulated user position during simulation
    LaunchedEffect(state.userLocation, state.isSimulating) {
        if (state.isSimulating && state.userLocation != null) {
            cameraPositionState.animate(
                CameraUpdateFactory.newLatLngZoom(state.userLocation!!, 19f), 800
            )
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        // Google Map
        GoogleMap(
            modifier = Modifier.fillMaxSize(),
            cameraPositionState = cameraPositionState,
            properties = MapProperties(
                mapType = MapType.NORMAL,
                isIndoorEnabled = true
            ),
            uiSettings = MapUiSettings(
                myLocationButtonEnabled = false,
                zoomControlsEnabled = true,
                indoorLevelPickerEnabled = true
            )
        ) {
            if (state.routePoints.isNotEmpty()) {
                Polyline(
                    points = state.routePoints,
                    color = Color(0xFF4285F4),
                    width = 12f
                )

                // End marker. Uses rose/pink so it doesn't collide with the
                // "full restroom = red" amenity-marker color — otherwise an
                // empty destination restroom looks like it's full.
                val endMarkerState = rememberMarkerState(
                    position = state.routePoints.last()
                )
                Marker(
                    state = endMarkerState,
                    title = state.destinationName ?: "Destination",
                    snippet = "Destination",
                    icon = BitmapDescriptorFactory.defaultMarker(BitmapDescriptorFactory.HUE_ROSE)
                )
            }

            // Amenity markers (filtered)
            val visibleAmenities = filteredAmenities(state)
            visibleAmenities.forEach { amenity ->
                // Include status + occupancy in the key so the marker is
                // recreated (not just recomposed) when those change. Works
                // around a maps-compose quirk where icon changes on an
                // already-placed marker don't always reach the native map.
                key(amenity.id, amenity.status, amenity.occupancy) {
                    val hue = amenityMarkerHue(amenity)
                    val pos = LatLng(amenity.latitude, amenity.longitude)
                    val markerState = rememberMarkerState(position = pos)
                    // Force-sync position so filtering doesn't leave a stale LatLng.
                    markerState.position = pos
                    Marker(
                        state = markerState,
                        title = amenity.name,
                        snippet = amenityMarkerSnippet(amenity),
                        icon = BitmapDescriptorFactory.defaultMarker(hue),
                        onClick = {
                            viewModel.selectAmenity(amenity)
                            true
                        }
                    )
                }
            }

            // User position marker (pulsing dot simulated with a circle + marker)
            state.userLocation?.let { loc ->
                Circle(
                    center = loc,
                    radius = 3.0,
                    fillColor = Color(0x554285F4),
                    strokeColor = Color(0xFF4285F4),
                    strokeWidth = 2f
                )
                val userMarkerState = rememberMarkerState(position = loc)
                LaunchedEffect(loc) { userMarkerState.position = loc }
                Marker(
                    state = userMarkerState,
                    title = "You",
                    icon = BitmapDescriptorFactory.defaultMarker(BitmapDescriptorFactory.HUE_AZURE),
                    anchor = androidx.compose.ui.geometry.Offset(0.5f, 0.5f)
                )
            }
        }

        // HUD card (top)
        if (state.isNavigating || state.isSimulating) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(12.dp)
                    .align(Alignment.TopCenter),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color(0xFF1A73E8))
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Directional arrow
                    Box(
                        modifier = Modifier
                            .size(48.dp)
                            .rotate(state.currentBearing),
                        contentAlignment = Alignment.Center
                    ) {
                        DirectionArrow()
                    }

                    Spacer(modifier = Modifier.width(12.dp))

                    Column(modifier = Modifier.weight(1f)) {
                        // Cardinal direction instruction
                        Text(
                            text = if (state.cardinalDirection.isNotEmpty())
                                "Head ${state.cardinalDirection}" else state.currentInstruction,
                            color = Color.White,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold
                        )
                        // Turn instruction
                        if (state.cardinalDirection.isNotEmpty()) {
                            Text(
                                text = state.currentInstruction,
                                color = Color(0xCCFFFFFF),
                                fontSize = 14.sp
                            )
                        }
                        // Distance to next node
                        if (state.distanceToNextMeters > 0) {
                            Text(
                                text = "%.0f m to next point".format(state.distanceToNextMeters),
                                color = Color(0xAAFFFFFF),
                                fontSize = 13.sp
                            )
                        }
                        // Destination name
                        state.destinationName?.let { name ->
                            Text(
                                text = "→ $name",
                                color = Color(0xAAFFFFFF),
                                fontSize = 13.sp
                            )
                        }
                    }
                }

                // Recalculating banner
                if (state.isRecalculating) {
                    Text(
                        text = "Recalculating...",
                        color = Color.Yellow,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                        textAlign = TextAlign.Center,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 8.dp)
                    )
                }
            }
        }

        // Amenity detail bottom sheet
        state.selectedAmenity?.let { amenity ->
            AmenityDetailSheet(
                amenity = amenity,
                onRouteHere = {
                    viewModel.routeToSpecificAmenity(amenity)
                    viewModel.clearSelectedAmenity()
                },
                onReport = {
                    reportPrefillAmenity = amenity
                    showReportsSheet = true
                    viewModel.clearSelectedAmenity()
                },
                onClose = { viewModel.clearSelectedAmenity() }
            )
        }

        // Fallback dialog if a cross-zone amenity ever slips past the filter.
        state.pendingCrossZoneAmenity?.let { amenity ->
            val destZone = amenity.zone ?: "other"
            val startZone = state.currentZone ?: "other"
            val implication = if (destZone == "secure")
                "you'll need to clear TSA security to reach it"
            else
                "you'll need to exit the secure area, and you'd have to " +
                    "re-clear TSA to come back"
            AlertDialog(
                onDismissRequest = { viewModel.cancelCrossZoneRoute() },
                title = { Text("Different zone") },
                text = {
                    Text(
                        "${amenity.name} is in the $destZone area, but " +
                            "you're in the $startZone area. To reach it, " +
                            "$implication. Continue anyway?"
                    )
                },
                confirmButton = {
                    TextButton(onClick = { viewModel.confirmCrossZoneRoute() }) {
                        Text("Continue")
                    }
                },
                dismissButton = {
                    TextButton(onClick = { viewModel.cancelCrossZoneRoute() }) {
                        Text("Cancel")
                    }
                }
            )
        }

        // UC5: route-start warning when the user taps a specific high/full restroom.
        state.pendingOccupancyWarning?.let { amenity ->
            val level = amenity.occupancy?.lowercase() ?: "high"
            val headline = if (level == "full") "This restroom is full."
                else "This restroom is high-occupancy."
            AlertDialog(
                onDismissRequest = { viewModel.dismissOccupancyWarning() },
                title = { Text("Destination is busy") },
                text = {
                    Text(
                        "$headline You can still route to ${amenity.name}, but " +
                            "the next-nearest restroom may be a better option. Route anyway?"
                    )
                },
                confirmButton = {
                    TextButton(onClick = { viewModel.confirmOccupancyWarning() }) {
                        Text("Route anyway")
                    }
                },
                dismissButton = {
                    TextButton(onClick = { viewModel.dismissOccupancyWarning() }) {
                        Text("Cancel")
                    }
                }
            )
        }

        // UC5 + UC7: mid-route prompt when the destination just became full/closed.
        state.pendingReroutePrompt?.let { prompt ->
            val reasonText = when (prompt.reason) {
                "full" -> "${prompt.originalDestinationName} just filled up."
                "closed" -> "${prompt.originalDestinationName} is now closed."
                else -> "${prompt.originalDestinationName} is no longer available."
            }
            AlertDialog(
                onDismissRequest = { viewModel.declineReroutePrompt() },
                title = { Text("Reroute?") },
                text = {
                    Text(
                        "$reasonText Reroute to the next-nearest ${prompt.amenityType}?"
                    )
                },
                confirmButton = {
                    TextButton(onClick = { viewModel.acceptReroutePrompt() }) {
                        Text("Reroute")
                    }
                },
                dismissButton = {
                    TextButton(onClick = { viewModel.declineReroutePrompt() }) {
                        Text("Keep going")
                    }
                }
            )
        }

        // Browse amenities bottom sheet
        if (state.showAmenityList) {
            AmenityListSheet(
                amenities = filteredAmenities(state),
                onSelect = { viewModel.selectAmenity(it); viewModel.toggleAmenityList() },
                onDismiss = { viewModel.toggleAmenityList() }
            )
        }

        // UC4: account chip — top-end. Hidden during navigation so it doesn't
        // overlap the HUD card. Tap opens LoginScreen or AccountSettingsScreen
        // depending on whether the user is signed in.
        if (!state.isNavigating && !state.isSimulating) {
            Card(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(12.dp)
                    .clickable { showAccountSheet = true },
                shape = RoundedCornerShape(20.dp)
            ) {
                Text(
                    text = if (authState.user != null)
                        "👤 ${authState.user!!.username}" else "👤 Sign in",
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp),
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium
                )
            }
        }

        if (showAccountSheet) {
            if (authState.user == null) {
                LoginScreen(
                    authViewModel = authViewModel,
                    onClose = { showAccountSheet = false }
                )
            } else {
                AccountSettingsScreen(
                    authViewModel = authViewModel,
                    onClose = { showAccountSheet = false },
                    onShowReports = {
                        showAccountSheet = false
                        reportPrefillAmenity = null
                        showReportsSheet = true
                    },
                    // Mirror the main map's Filters toggle so editing prefs
                    // here applies to the map immediately AND syncs to the
                    // backend, instead of just reading as static text.
                    accessibilityModeOn = state.accessibilityMode,
                    onAccessibilityToggle = { newValue ->
                        if (state.accessibilityMode != newValue) {
                            viewModel.toggleAccessibilityMode()
                        }
                        authViewModel.persistWheelchairPref(newValue)
                    },
                )
            }
        }

        if (showReportsSheet) {
            ReportsScreen(
                reportsViewModel = reportsViewModel,
                isLoggedIn = authState.user != null,
                amenities = state.amenities,
                prefilledAmenity = reportPrefillAmenity,
                onClose = {
                    showReportsSheet = false
                    reportPrefillAmenity = null
                    reportsViewModel.clearMessages()
                }
            )
        }

        // Bottom control panel
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp)
                .align(Alignment.BottomCenter),
            shape = RoundedCornerShape(16.dp)
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                // Error display
                if (state.error != null) {
                    Text(
                        text = state.error!!,
                        color = Color.Red,
                        fontSize = 13.sp,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                }

                if (state.isLoading) {
                    CircularProgressIndicator(modifier = Modifier.padding(8.dp))
                }

                if (!state.isNavigating && !state.isSimulating) {
                    Text(
                        text = "Terminal D Navigation",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 12.dp)
                    )

                    if (state.currentZone != null) {
                        FiltersSection(
                            state = state,
                            viewModel = viewModel,
                            onAccessibilityToggle = { newValue ->
                                viewModel.toggleAccessibilityMode()
                                // Best-effort backend persist; no-op when guest.
                                authViewModel.persistWheelchairPref(newValue)
                            }
                        )
                        Spacer(modifier = Modifier.height(8.dp))

                        // Amenity type dropdown (filters the map to a single type)
                        if (state.amenityTypes.isNotEmpty()) {
                            AmenityDropdown(
                                amenityTypes = state.amenityTypes,
                                selected = state.dropdownTypeFilter,
                                onSelect = { viewModel.setDropdownTypeFilter(it) },
                                onClear = { viewModel.setDropdownTypeFilter(null) }
                            )
                            Spacer(modifier = Modifier.height(8.dp))

                            // Restroom gender sub-filter
                            if (state.dropdownTypeFilter == "restroom") {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                                ) {
                                    FilterChip(
                                        selected = state.restroomGenderFilter == RestroomGender.ANY,
                                        onClick = { viewModel.setRestroomGender(RestroomGender.ANY) },
                                        label = { Text("Any") }
                                    )
                                    FilterChip(
                                        selected = state.restroomGenderFilter == RestroomGender.MALE,
                                        onClick = { viewModel.setRestroomGender(RestroomGender.MALE) },
                                        label = { Text("Male") }
                                    )
                                    FilterChip(
                                        selected = state.restroomGenderFilter == RestroomGender.FEMALE,
                                        onClick = { viewModel.setRestroomGender(RestroomGender.FEMALE) },
                                        label = { Text("Female") }
                                    )
                                }
                                Spacer(modifier = Modifier.height(8.dp))
                            }

                            // Route-to-nearest button (only when a type is selected)
                            if (state.dropdownTypeFilter != null) {
                                Button(
                                    onClick = {
                                        val type = state.dropdownTypeFilter
                                        if (type == "restroom" &&
                                            state.restroomGenderFilter != RestroomGender.ANY
                                        ) {
                                            viewModel.routeToNearestFilteredRestroom()
                                        } else if (type != null) {
                                            viewModel.routeToAmenity(type)
                                        }
                                    },
                                    modifier = Modifier.fillMaxWidth(),
                                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1A73E8))
                                ) {
                                    Text("Route to nearest", fontSize = 16.sp)
                                }
                                Spacer(modifier = Modifier.height(8.dp))
                            }
                        }

                        Button(
                            onClick = { viewModel.toggleAmenityList() },
                            modifier = Modifier.fillMaxWidth(),
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF34A853))
                        ) {
                            Text("Browse Amenities", fontSize = 16.sp)
                        }
                        Spacer(modifier = Modifier.height(8.dp))
                    } else {
                        // Hide picker until the user chooses a zone — prevents wrong-zone routes.
                        Text(
                            text = "Pick your starting area to begin.",
                            fontSize = 14.sp,
                            color = Color.Gray,
                            textAlign = TextAlign.Center,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(bottom = 12.dp)
                        )
                    }

                    // Test buttons: drop the user at a random node in the chosen zone.
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Button(
                            onClick = { viewModel.setMockStart("secure") },
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1A73E8))
                        ) {
                            Text("Start in Secure Area", fontSize = 14.sp)
                        }
                        Button(
                            onClick = { viewModel.setMockStart("public") },
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1A73E8))
                        ) {
                            Text("Start in Public Area", fontSize = 14.sp)
                        }
                    }
                } else {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                text = if (state.isSimulating) "Simulating..." else "Route ready",
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Step ${state.currentWaypointIndex + 1} / ${state.waypoints.size}",
                                color = Color.Gray,
                                fontSize = 14.sp
                            )
                        }
                        Button(
                            onClick = { viewModel.stopNavigation() },
                            colors = ButtonDefaults.buttonColors(containerColor = Color.Red)
                        ) {
                            Text("Stop")
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        // Start / Resume simulation
                        if (!state.isSimulating) {
                            Button(
                                onClick = { viewModel.startSimulation() },
                                modifier = Modifier.weight(1f),
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF34A853))
                            ) {
                                Text("Simulate")
                            }
                        }

                        // Go off-path button
                        Button(
                            onClick = { viewModel.goOffPath() },
                            modifier = Modifier.weight(1f),
                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFFF9800))
                        ) {
                            Text("Go Off Path")
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AmenityDropdown(
    amenityTypes: List<String>,
    selected: String?,
    onSelect: (String) -> Unit,
    onClear: () -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    val displayText = selected?.replaceFirstChar { it.uppercase() }
        ?: "Select amenity type..."

    ExposedDropdownMenuBox(
        expanded = expanded,
        onExpandedChange = { expanded = !expanded }
    ) {
        OutlinedTextField(
            value = displayText,
            onValueChange = {},
            readOnly = true,
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(MenuAnchorType.PrimaryNotEditable)
        )
        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false }
        ) {
            DropdownMenuItem(
                text = { Text("Clear filter", fontWeight = FontWeight.Bold) },
                onClick = {
                    expanded = false
                    onClear()
                }
            )
            amenityTypes.forEach { type ->
                DropdownMenuItem(
                    text = { Text(type.replaceFirstChar { it.uppercase() }) },
                    onClick = {
                        expanded = false
                        onSelect(type)
                    }
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class, androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun FiltersSection(
    state: NavigationState,
    viewModel: NavigationViewModel,
    onAccessibilityToggle: (Boolean) -> Unit = { viewModel.toggleAccessibilityMode() }
) {
    var expanded by remember { mutableStateOf(false) }

    Column(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable { expanded = !expanded }
                .padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = if (expanded) "▼ Filters" else "▶ Filters",
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold
            )
            val active = listOfNotNull(
                if (state.accessibilityMode) "♿" else null,
                if (state.activeTypeFilters.isNotEmpty()) "${state.activeTypeFilters.size} types" else null
            ).joinToString(" · ")
            if (active.isNotEmpty()) {
                Text(text = active, fontSize = 12.sp, color = Color.Gray)
            }
        }

        if (expanded) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Switch(
                    checked = state.accessibilityMode,
                    onCheckedChange = { onAccessibilityToggle(it) }
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text("Wheelchair accessible only", fontSize = 14.sp)
            }

            if (state.amenityTypes.isNotEmpty()) {
                androidx.compose.foundation.layout.FlowRow(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    state.amenityTypes.forEach { type ->
                        val selected = type in state.activeTypeFilters
                        FilterChip(
                            selected = selected,
                            onClick = { viewModel.setTypeFilter(type, !selected) },
                            label = { Text(type.replaceFirstChar { it.uppercase() }, fontSize = 12.sp) }
                        )
                    }
                }
            }
        }
    }
}

/**
 * Marker hue for an amenity.
 *
 * Admin-set status wins when it's non-active (closed / out_of_service / maintenance),
 * so a staffer can always pick those out at a glance. Otherwise, for restrooms,
 * the marker gradients with occupancy: green → yellow → orange → red as it
 * fills up. Non-restrooms ignore occupancy (they don't track it) and stay green
 * unless their status is "busy".
 */
internal fun amenityMarkerHue(amenity: Amenity): Float {
    val status = amenity.status.lowercase()
    if (status == "closed" || status == "out_of_service") {
        return BitmapDescriptorFactory.HUE_VIOLET
    }
    if (status == "maintenance" || status == "cleaning") {
        return BitmapDescriptorFactory.HUE_ORANGE
    }
    if (status == "busy") {
        return BitmapDescriptorFactory.HUE_YELLOW
    }
    // status == open (or unknown) — restrooms gradient by occupancy bucket.
    return when (amenity.occupancy?.lowercase()) {
        "full" -> BitmapDescriptorFactory.HUE_RED
        "high" -> BitmapDescriptorFactory.HUE_ORANGE
        "medium" -> BitmapDescriptorFactory.HUE_YELLOW
        "low", "empty" -> BitmapDescriptorFactory.HUE_GREEN
        else -> BitmapDescriptorFactory.HUE_GREEN    // non-restrooms / unknown
    }
}

/**
 * One-line snippet under an amenity marker. For restrooms, surfaces live
 * occupancy bucket and crowd bucket. Other types keep the original compact form.
 */
internal fun amenityMarkerSnippet(amenity: Amenity): String {
    if (amenity.type != "restroom") {
        return "${amenity.type} · ${amenity.status}"
    }
    val parts = mutableListOf(amenity.status)
    amenity.occupancy?.takeIf { it.isNotBlank() }?.let { parts.add("occ: $it") }
    amenity.crowdlevel?.let { parts.add("wait: ${crowdBucketLabel(it)}") }
    return parts.joinToString(" · ")
}

/** Bucket a 0..100 crowd level into Low / Moderate / Heavy for display. */
internal fun crowdBucketLabel(level: Int): String = when {
    level < 34 -> "Low"
    level < 67 -> "Moderate"
    else -> "Heavy"
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AmenityDetailSheet(
    amenity: Amenity,
    onRouteHere: () -> Unit,
    onReport: () -> Unit,
    onClose: () -> Unit
) {
    val isAccessible = amenity.has_accessible_unit == true ||
        amenity.wheelchairaccessible.equals("yes", ignoreCase = true)
    val isRestroom = amenity.type == "restroom"

    ModalBottomSheet(onDismissRequest = onClose) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Text(amenity.name, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Spacer(modifier = Modifier.height(4.dp))
            Text(amenity.type.replaceFirstChar { it.uppercase() }, fontSize = 14.sp, color = Color.Gray)
            Spacer(modifier = Modifier.height(8.dp))
            Text("Status: ${amenity.status}", fontSize = 14.sp)
            if (isRestroom) {
                amenity.occupancy?.takeIf { it.isNotBlank() }?.let { bucket ->
                    val color = when (bucket) {
                        "full" -> Color(0xFFD32F2F)
                        "high" -> Color(0xFFF57C00)
                        "medium" -> Color(0xFFF9A825)
                        "low" -> Color(0xFF2E7D32)
                        "empty" -> Color(0xFF2E7D32)
                        else -> Color.Gray
                    }
                    Text(
                        "Occupancy: ${bucket.replaceFirstChar { it.uppercase() }}",
                        fontSize = 14.sp,
                        color = color
                    )
                }
                amenity.crowdlevel?.let { level ->
                    Text("Wait: ${crowdBucketLabel(level)} ($level)", fontSize = 14.sp)
                }
            }
            Text(
                text = if (isAccessible) "♿ Wheelchair accessible" else "Not wheelchair accessible",
                fontSize = 14.sp,
                color = if (isAccessible) Color(0xFF2E7D32) else Color.Gray
            )
            Spacer(modifier = Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = onRouteHere,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1A73E8))
                ) { Text("Route Here") }
                OutlinedButton(
                    onClick = onClose,
                    modifier = Modifier.weight(1f)
                ) { Text("Close") }
            }
            Spacer(modifier = Modifier.height(8.dp))
            // UC3 entry point: pre-fills the report form with this amenity.
            OutlinedButton(
                onClick = onReport,
                modifier = Modifier.fillMaxWidth()
            ) { Text("Report a problem") }
            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AmenityListSheet(
    amenities: List<Amenity>,
    onSelect: (Amenity) -> Unit,
    onDismiss: () -> Unit
) {
    ModalBottomSheet(onDismissRequest = onDismiss) {
        Column(modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp)) {
            Text(
                "Amenities (${amenities.size})",
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(bottom = 8.dp)
            )
            LazyColumn(modifier = Modifier.fillMaxWidth().heightIn(max = 480.dp)) {
                items(amenities, key = { it.id }) { amenity ->
                    val isAccessible = amenity.has_accessible_unit == true ||
                        amenity.wheelchairaccessible.equals("yes", ignoreCase = true)
                    // Match the map marker hue so the list and map agree at a glance.
                    val statusColor = when (amenity.status.lowercase()) {
                        "closed", "out_of_service" -> Color(0xFF9C27B0)    // violet
                        "maintenance", "cleaning" -> Color(0xFFFF9800)     // orange
                        "busy" -> Color(0xFFFFC107)                        // yellow
                        else -> when (amenity.occupancy?.lowercase()) {    // open + restroom gradient
                            "full" -> Color(0xFFD32F2F)
                            "high" -> Color(0xFFF57C00)
                            "medium" -> Color(0xFFF9A825)
                            else -> Color(0xFF34A853)                      // low / empty / non-restroom
                        }
                    }
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { onSelect(amenity) }
                            .padding(vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            modifier = Modifier
                                .size(10.dp)
                                .background(statusColor, CircleShape)
                        )
                        Spacer(modifier = Modifier.width(12.dp))
                        Column(modifier = Modifier.weight(1f)) {
                            Text(amenity.name, fontSize = 15.sp, fontWeight = FontWeight.Medium)
                            Text(
                                "${amenity.type} · ${amenity.status}",
                                fontSize = 12.sp,
                                color = Color.Gray
                            )
                        }
                        if (isAccessible) {
                            Text("♿", fontSize = 18.sp)
                        }
                    }
                    HorizontalDivider()
                }
            }
            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}

@Composable
fun DirectionArrow() {
    Canvas(modifier = Modifier.size(36.dp)) {
        val w = size.width
        val h = size.height
        val path = Path().apply {
            moveTo(w / 2f, 0f)
            lineTo(w * 0.85f, h * 0.85f)
            lineTo(w / 2f, h * 0.6f)
            lineTo(w * 0.15f, h * 0.85f)
            close()
        }
        drawPath(path, color = Color.White)
    }
}
