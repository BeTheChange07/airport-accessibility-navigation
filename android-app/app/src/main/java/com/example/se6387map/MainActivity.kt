package com.example.se6387map

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.app.ActivityCompat
import androidx.lifecycle.viewmodel.compose.viewModel
import com.google.android.gms.location.*
import com.google.android.gms.maps.model.BitmapDescriptorFactory
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.maps.android.compose.*

class MainActivity : ComponentActivity() {

    private lateinit var fusedLocationClient: FusedLocationProviderClient
    private var locationCallback: LocationCallback? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        fusedLocationClient = LocationServices.getFusedLocationProviderClient(this)

        // Request location permissions
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

                // Start location updates when we have permission
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
                result.lastLocation?.let { location ->
                    // This will be picked up by the ViewModel
                    // We'll connect this in the Composable
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

    // Terminal D center coordinates
    val terminalD = LatLng(32.8980, -97.0435)
    val cameraPositionState = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(terminalD, 18f)
    }

    Box(modifier = Modifier.fillMaxSize()) {
        // Google Map
        GoogleMap(
            modifier = Modifier.fillMaxSize(),
            cameraPositionState = cameraPositionState,
            properties = MapProperties(
                isMyLocationEnabled = true,
                mapType = MapType.NORMAL,
                isIndoorEnabled = true
            ),
            uiSettings = MapUiSettings(
                myLocationButtonEnabled = true,
                zoomControlsEnabled = true,
                indoorLevelPickerEnabled = true
            )
        ) {
            // Draw navigation route
            if (state.routePoints.isNotEmpty()) {
                Polyline(
                    points = state.routePoints,
                    color = Color(0xFF4285F4),
                    width = 12f
                )

                // Start marker
                Marker(
                    state = MarkerState(position = state.routePoints.first()),
                    title = "Start",
                    icon = BitmapDescriptorFactory.defaultMarker(BitmapDescriptorFactory.HUE_GREEN)
                )

                // End marker
                Marker(
                    state = MarkerState(position = state.routePoints.last()),
                    title = "Destination",
                    icon = BitmapDescriptorFactory.defaultMarker(BitmapDescriptorFactory.HUE_RED)
                )
            }
        }

        // Turn-by-turn instruction bar at top
        if (state.isNavigating) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp)
                    .align(Alignment.TopCenter),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(
                    containerColor = Color(0xFF1A73E8)
                )
            ) {
                Text(
                    text = state.currentInstruction,
                    color = Color.White,
                    fontSize = 20.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(20.dp)
                )
            }
        }

        // Bottom panel with demo route button
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp)
                .align(Alignment.BottomCenter),
            shape = RoundedCornerShape(12.dp)
        ) {
            Column(
                modifier = Modifier.padding(16.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                if (state.error != null) {
                    Text(
                        text = state.error!!,
                        color = Color.Red,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                }

                if (state.isLoading) {
                    CircularProgressIndicator(modifier = Modifier.padding(8.dp))
                }

                if (!state.isNavigating) {
                    Text(
                        text = "Terminal D Navigation",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 12.dp)
                    )

                    // Demo: navigate from node 1425 to node 16733
                    Button(
                        onClick = { viewModel.fetchRoute(1425, 16733) },
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Color(0xFF1A73E8)
                        )
                    ) {
                        Text("Demo Route (1425 to 16733)", fontSize = 16.sp)
                    }
                } else {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                text = "Navigating...",
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "${state.waypoints.size} waypoints",
                                color = Color.Gray,
                                fontSize = 14.sp
                            )
                        }
                        Button(
                            onClick = { viewModel.stopNavigation() },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Color.Red
                            )
                        ) {
                            Text("Stop")
                        }
                    }
                }
            }
        }
    }
}
