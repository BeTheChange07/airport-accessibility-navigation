package com.example.se6387map

import com.google.android.gms.maps.model.LatLng
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test

/** Synchronous ViewModel state-transition tests (no Retrofit calls). */
class NavigationStateTest {

    private fun amenity(
        id: Int,
        zone: String?,
    ) = Amenity(
        id = id,
        nodeid = 100 + id,
        name = "Amenity $id",
        type = "food",
        latitude = 32.9,
        longitude = -97.0,
        status = "open",
        wheelchairaccessible = null,
        has_accessible_unit = null,
        zone = zone,
    )

    @Test
    fun isOffPath_freshViewModel_returnsFalse_noRoute() {
        // Empty route should always be "on path" — guards against crashes before a route loads.
        val vm = NavigationViewModel()
        assertFalse(vm.isOffPath(LatLng(32.9, -97.0)))
    }

    @Test
    fun setDropdownTypeFilter_resetsGenderWhenTypeChanges() {
        val vm = NavigationViewModel()
        vm.setDropdownTypeFilter("restroom")
        vm.setRestroomGender(RestroomGender.MALE)
        assertEquals(RestroomGender.MALE, vm.state.value.restroomGenderFilter)
        vm.setDropdownTypeFilter("food")
        assertEquals(RestroomGender.ANY, vm.state.value.restroomGenderFilter)
    }

    @Test
    fun routeToSpecificAmenity_crossZone_parksAmenityInsteadOfRouting() {
        val vm = NavigationViewModel()
        vm.seedStartForTest(LatLng(32.9, -97.0), zone = "secure")
        assertNull(vm.state.value.pendingCrossZoneAmenity)

        vm.routeToSpecificAmenity(amenity(1, zone = "public"))
        val parked = vm.state.value.pendingCrossZoneAmenity
        assertNotNull(parked)
        assertEquals(1, parked!!.id)
        assertEquals("public", parked.zone)
        assertEquals(0, vm.state.value.routePoints.size)
        assertFalse(vm.state.value.isNavigating)
    }

    @Test
    fun cancelCrossZoneRoute_clearsParkedAmenity() {
        val vm = NavigationViewModel()
        vm.seedStartForTest(LatLng(32.9, -97.0), zone = "secure")
        vm.routeToSpecificAmenity(amenity(1, zone = "public"))
        assertNotNull(vm.state.value.pendingCrossZoneAmenity)

        vm.cancelCrossZoneRoute()
        assertNull(vm.state.value.pendingCrossZoneAmenity)
    }
}
