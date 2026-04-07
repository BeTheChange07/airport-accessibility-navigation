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

                    viewModel.setMockLocation()
                    viewModel.loadAmenityTypes()
                    viewModel.loadAmenities()
                }

                NavigationScreen(viewModel = viewModel)
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
fun NavigationScreen(viewModel: NavigationViewModel) {
    val state by viewModel.state.collectAsState()

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
        // ── Google Map ─────────────────────────────────────────────
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
            // Draw navigation route polyline
            if (state.routePoints.isNotEmpty()) {
                Polyline(
                    points = state.routePoints,
                    color = Color(0xFF4285F4),
                    width = 12f
                )

                // End marker
                val endMarkerState = rememberMarkerState(
                    position = state.routePoints.last()
                )
                Marker(
                    state = endMarkerState,
                    title = state.destinationName ?: "Destination",
                    icon = BitmapDescriptorFactory.defaultMarker(BitmapDescriptorFactory.HUE_RED)
                )
            }

            // Amenity markers (filtered)
            val visibleAmenities = filteredAmenities(state)
            visibleAmenities.forEach { amenity ->
                key(amenity.id) {
                    val hue = when (amenity.status.lowercase()) {
                        "open" -> BitmapDescriptorFactory.HUE_GREEN
                        "closed" -> BitmapDescriptorFactory.HUE_VIOLET
                        "maintenance", "cleaning" -> BitmapDescriptorFactory.HUE_ORANGE
                        else -> BitmapDescriptorFactory.HUE_YELLOW
                    }
                    val pos = LatLng(amenity.latitude, amenity.longitude)
                    val markerState = rememberMarkerState(position = pos)
                    // rememberMarkerState's `position` is initial-only; force-sync it
                    // each recomposition so filtering doesn't leave a stale LatLng behind.
                    markerState.position = pos
                    Marker(
                        state = markerState,
                        title = amenity.name,
                        snippet = "${amenity.type} · ${amenity.status}",
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

        // ── HUD Card (top) ─────────────────────────────────────────
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

        // ── Amenity detail bottom sheet ────────────────────────────
        state.selectedAmenity?.let { amenity ->
            AmenityDetailSheet(
                amenity = amenity,
                onRouteHere = {
                    viewModel.routeToSpecificAmenity(amenity)
                    viewModel.clearSelectedAmenity()
                },
                onClose = { viewModel.clearSelectedAmenity() }
            )
        }

        // ── Browse amenities bottom sheet ──────────────────────────
        if (state.showAmenityList) {
            AmenityListSheet(
                amenities = filteredAmenities(state),
                onSelect = { viewModel.selectAmenity(it); viewModel.toggleAmenityList() },
                onDismiss = { viewModel.toggleAmenityList() }
            )
        }

        // ── Bottom control panel ───────────────────────────────────
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
                    // ── Not navigating: show amenity picker + demo ──────
                    Text(
                        text = "Terminal D Navigation",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 12.dp)
                    )

                    // Filters section
                    FiltersSection(state = state, viewModel = viewModel)
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

                    // Demo route button
                    Button(
                        onClick = { viewModel.fetchRoute(1262, 1769) },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1A73E8))
                    ) {
                        Text("Demo Route (1262 → 1769)", fontSize = 16.sp)
                    }
                } else {
                    // ── Navigating: simulation controls ─────────────────
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

// ── Amenity type dropdown ──────────────────────────────────────────

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

// ── Filters section ────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class, androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
fun FiltersSection(state: NavigationState, viewModel: NavigationViewModel) {
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
                    onCheckedChange = { viewModel.toggleAccessibilityMode() }
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

// ── Amenity detail sheet ───────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AmenityDetailSheet(amenity: Amenity, onRouteHere: () -> Unit, onClose: () -> Unit) {
    val isAccessible = amenity.has_accessible_unit == true ||
        amenity.wheelchairaccessible.equals("yes", ignoreCase = true)

    ModalBottomSheet(onDismissRequest = onClose) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Text(amenity.name, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Spacer(modifier = Modifier.height(4.dp))
            Text(amenity.type.replaceFirstChar { it.uppercase() }, fontSize = 14.sp, color = Color.Gray)
            Spacer(modifier = Modifier.height(8.dp))
            Text("Status: ${amenity.status}", fontSize = 14.sp)
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
            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}

// ── Amenity list sheet ─────────────────────────────────────────────

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
                    val statusColor = when (amenity.status.lowercase()) {
                        "open" -> Color(0xFF34A853)
                        "closed" -> Color(0xFF9E9E9E)
                        "maintenance", "cleaning" -> Color(0xFFFF9800)
                        else -> Color(0xFFFFC107)
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

// ── Direction arrow drawn with Canvas ──────────────────────────────

@Composable
fun DirectionArrow() {
    Canvas(modifier = Modifier.size(36.dp)) {
        val w = size.width
        val h = size.height
        val path = Path().apply {
            moveTo(w / 2f, 0f)          // top center (points up = North)
            lineTo(w * 0.85f, h * 0.85f) // bottom right
            lineTo(w / 2f, h * 0.6f)     // inner notch
            lineTo(w * 0.15f, h * 0.85f) // bottom left
            close()
        }
        drawPath(path, color = Color.White)
    }
}
