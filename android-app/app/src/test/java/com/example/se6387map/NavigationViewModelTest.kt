package com.example.se6387map

import com.google.android.gms.maps.model.LatLng
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class NavigationViewModelTest {

    private fun amenity(
        id: Int,
        type: String,
        status: String = "open",
        accessibleUnit: Boolean? = null,
        wheelchairaccessible: String? = null,
        name: String = "Amenity $id",
        zone: String = "secure"
    ) = Amenity(
        id = id,
        nodeid = 100 + id,
        name = name,
        type = type,
        latitude = 32.9,
        longitude = -97.0,
        status = status,
        wheelchairaccessible = wheelchairaccessible,
        has_accessible_unit = accessibleUnit,
        zone = zone
    )

    @Test
    fun filteredAmenities_noFilters_returnsAll() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, "restroom"),
                amenity(2, "food")
            ),
            currentZone = "secure"
        )
        assertEquals(2, filteredAmenities(state).size)
    }

    @Test
    fun filteredAmenities_typeFilter_keepsOnlyMatchingTypes() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, "restroom"),
                amenity(2, "food"),
                amenity(3, "restroom")
            ),
            activeTypeFilters = setOf("restroom"),
            currentZone = "secure"
        )
        val result = filteredAmenities(state)
        assertEquals(2, result.size)
        assertTrue(result.all { it.type == "restroom" })
    }

    @Test
    fun filteredAmenities_accessibilityMode_viaAccessibleUnit() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, "restroom", accessibleUnit = true),
                amenity(2, "restroom", accessibleUnit = false)
            ),
            accessibilityMode = true,
            currentZone = "secure"
        )
        val result = filteredAmenities(state)
        assertEquals(1, result.size)
        assertEquals(1, result[0].id)
    }

    @Test
    fun filteredAmenities_accessibilityMode_viaAmenityFlag() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, "food", wheelchairaccessible = "yes"),
                amenity(2, "food", wheelchairaccessible = "no")
            ),
            accessibilityMode = true,
            currentZone = "secure"
        )
        val result = filteredAmenities(state)
        assertEquals(1, result.size)
        assertEquals(1, result[0].id)
    }

    @Test
    fun filteredAmenities_accessibilityMode_caseInsensitive() {
        val state = NavigationState(
            amenities = listOf(amenity(1, "food", wheelchairaccessible = "YES")),
            accessibilityMode = true,
            currentZone = "secure"
        )
        assertEquals(1, filteredAmenities(state).size)
    }

    @Test
    fun filteredAmenities_combinedFilters() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, "restroom", accessibleUnit = true),
                amenity(2, "restroom", accessibleUnit = false),
                amenity(3, "food", accessibleUnit = true)
            ),
            activeTypeFilters = setOf("restroom"),
            accessibilityMode = true,
            currentZone = "secure"
        )
        val result = filteredAmenities(state)
        assertEquals(1, result.size)
        assertEquals(1, result[0].id)
    }

    @Test
    fun pointOnSegment_isZero() {
        val vm = NavigationViewModel()
        val a = LatLng(32.9000, -97.0000)
        val b = LatLng(32.9010, -97.0000)
        val mid = LatLng(32.9005, -97.0000)
        val d = vm.pointToSegmentDistanceMeters(mid, a, b)
        assertTrue("distance should be ~0 but was $d", d < 0.5)
    }

    @Test
    fun pointBeyondSegmentEnd_clampsToEndpoint() {
        val vm = NavigationViewModel()
        val a = LatLng(0.0, 0.0)
        val b = LatLng(0.0, 0.001)
        val p = LatLng(0.0, 0.002)
        val d = vm.pointToSegmentDistanceMeters(p, a, b)
        assertTrue("expected ~111m, got $d", d in 100.0..120.0)
    }

    @Test
    fun pointPerpendicularToSegment_returnsPerpDistance() {
        val vm = NavigationViewModel()
        val a = LatLng(0.0, 0.0)
        val b = LatLng(0.0, 1.0)
        val p = LatLng(1.0, 0.5)
        val d = vm.pointToSegmentDistanceMeters(p, a, b)
        assertTrue("expected ~111km, got $d", d in 100_000.0..120_000.0)
    }

    @Test
    fun degeneratedSegment_returnsDistanceToPoint() {
        val vm = NavigationViewModel()
        val a = LatLng(0.0, 0.0)
        val p = LatLng(0.0, 0.001)
        val d = vm.pointToSegmentDistanceMeters(p, a, a)
        assertTrue(d in 100.0..120.0)
    }

    @Test
    fun filteredAmenities_dropdownTypeFilter_keepsOnlyThatType() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, "restroom", name = "Male Bathroom"),
                amenity(2, "food", name = "Cafe"),
                amenity(3, "restroom", name = "Female Bathroom")
            ),
            dropdownTypeFilter = "restroom",
            currentZone = "secure"
        )
        val result = filteredAmenities(state)
        assertEquals(2, result.size)
        assertTrue(result.all { it.type == "restroom" })
    }

    @Test
    fun filteredAmenities_restroomGenderMale_keepsOnlyMale() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, "restroom", name = "Male Bathroom"),
                amenity(2, "restroom", name = "Female Bathroom")
            ),
            dropdownTypeFilter = "restroom",
            restroomGenderFilter = RestroomGender.MALE,
            currentZone = "secure"
        )
        val result = filteredAmenities(state)
        assertEquals(1, result.size)
        assertEquals("Male Bathroom", result[0].name)
    }

    @Test
    fun filteredAmenities_restroomGenderFemale_keepsOnlyFemale() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, "restroom", name = "Male Bathroom"),
                amenity(2, "restroom", name = "Female Bathroom")
            ),
            dropdownTypeFilter = "restroom",
            restroomGenderFilter = RestroomGender.FEMALE,
            currentZone = "secure"
        )
        val result = filteredAmenities(state)
        assertEquals(1, result.size)
        // "Female" must not match a naive "male" substring check.
        assertEquals("Female Bathroom", result[0].name)
    }

    @Test
    fun filteredAmenities_restroomGenderAny_keepsBoth() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, "restroom", name = "Male Bathroom"),
                amenity(2, "restroom", name = "Female Bathroom")
            ),
            dropdownTypeFilter = "restroom",
            restroomGenderFilter = RestroomGender.ANY,
            currentZone = "secure"
        )
        assertEquals(2, filteredAmenities(state).size)
    }

    @Test
    fun filteredAmenities_combinesWithAccessibilityMode() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, "restroom", name = "Male Bathroom", accessibleUnit = true),
                amenity(2, "restroom", name = "Male Bathroom", accessibleUnit = false),
                amenity(3, "restroom", name = "Female Bathroom", accessibleUnit = true)
            ),
            dropdownTypeFilter = "restroom",
            restroomGenderFilter = RestroomGender.MALE,
            accessibilityMode = true,
            currentZone = "secure"
        )
        val result = filteredAmenities(state)
        assertEquals(1, result.size)
        assertEquals(1, result[0].id)
    }

    @Test
    fun accessibilityMode_doesNotFilter_whenOff() {
        val state = NavigationState(
            amenities = listOf(amenity(1, "food", accessibleUnit = false)),
            accessibilityMode = false,
            currentZone = "secure"
        )
        assertFalse(filteredAmenities(state).isEmpty())
    }

    /**
     * Validates the per-status routing decision for every value the admin
     * dropdown can write. open/busy go straight to the route call, while
     * closed/maintenance/out_of_service must park in pendingClosedAmenity so
     * the dialog can offer a reroute. Keeps the mobile side and the backend
     * `a.status IN ('open','busy')` SQL filter aligned.
     */
    private fun seededVm(targetStatus: String, occupancy: String? = null): NavigationViewModel {
        val vm = NavigationViewModel()
        vm.seedStartForTest(LatLng(32.9, -97.0), "secure")
        return vm
    }

    @Test
    fun routeToSpecificAmenity_blocksClosed() {
        val vm = seededVm("closed")
        vm.routeToSpecificAmenity(amenity(1, "restroom", status = "closed"))
        assertEquals(1, vm.state.value.pendingClosedAmenity?.id)
    }

    @Test
    fun routeToSpecificAmenity_blocksMaintenance() {
        val vm = seededVm("maintenance")
        vm.routeToSpecificAmenity(amenity(1, "restroom", status = "maintenance"))
        assertEquals(1, vm.state.value.pendingClosedAmenity?.id)
    }

    @Test
    fun routeToSpecificAmenity_blocksOutOfService() {
        val vm = seededVm("out_of_service")
        vm.routeToSpecificAmenity(amenity(1, "restroom", status = "out_of_service"))
        assertEquals(1, vm.state.value.pendingClosedAmenity?.id)
    }

    // open/busy are intentionally NOT covered here: they fall through to
    // `executeRouteToAmenity` which spins up a viewModelScope coroutine and
    // needs Dispatchers.Main set up. The backend test
    // TestGenerateRouteToAmenity.test_status_filter_for_each_dropdown_value
    // already pins that those two values reach the dijkstra path.

    @Test
    fun pauseSimulation_isNoopWhenNotSimulating() {
        // Pause must not flip the paused flag if the walker isn't actually
        // running — otherwise a stray Pause click on a fresh route would hide
        // the Simulate button behind a fake Resume.
        val vm = NavigationViewModel()
        vm.pauseSimulation()
        assertFalse(vm.state.value.isSimulationPaused)
    }

    @Test
    fun stopSimulation_clearsPausedFlag() {
        // Stop is the hard exit; it must clear isSimulationPaused even if the
        // walker was paused, so the next route doesn't open with a bogus
        // Resume button.
        val vm = NavigationViewModel()
        // Force the paused state so we can verify stopSimulation wipes it.
        val state = vm.state as kotlinx.coroutines.flow.MutableStateFlow<NavigationState>
        state.value = state.value.copy(isSimulationPaused = true)
        vm.stopSimulation()
        assertFalse(vm.state.value.isSimulationPaused)
    }
}
