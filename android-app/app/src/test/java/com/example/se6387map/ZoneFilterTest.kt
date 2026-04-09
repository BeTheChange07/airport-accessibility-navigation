package com.example.se6387map

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Tests the zone branch of filteredAmenities — must not leak across TSA. */
class ZoneFilterTest {

    private fun amenity(
        id: Int,
        type: String = "food",
        zone: String? = null
    ) = Amenity(
        id = id,
        nodeid = 100 + id,
        name = "Amenity $id",
        type = type,
        latitude = 32.9,
        longitude = -97.0,
        status = "open",
        wheelchairaccessible = null,
        has_accessible_unit = null,
        zone = zone
    )

    @Test
    fun currentZoneNull_hidesAllAmenities() {
        // Until the user picks a zone, the list must be empty.
        val state = NavigationState(
            amenities = listOf(
                amenity(1, zone = "secure"),
                amenity(2, zone = "public"),
                amenity(3, zone = null)
            ),
            currentZone = null
        )
        assertTrue(filteredAmenities(state).isEmpty())
    }

    @Test
    fun currentZoneSecure_keepsOnlySecureAmenities() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, zone = "secure"),
                amenity(2, zone = "public"),
                amenity(3, zone = "secure")
            ),
            currentZone = "secure"
        )
        val result = filteredAmenities(state)
        assertEquals(2, result.size)
        assertTrue(result.all { it.zone == "secure" })
    }

    @Test
    fun currentZonePublic_keepsOnlyPublicAmenities() {
        val state = NavigationState(
            amenities = listOf(
                amenity(1, zone = "secure"),
                amenity(2, zone = "public")
            ),
            currentZone = "public"
        )
        val result = filteredAmenities(state)
        assertEquals(1, result.size)
        assertEquals("public", result[0].zone)
    }

    @Test
    fun currentZoneSet_dropsAmenitiesWithNullZone() {
        // Strict equality (a.zone == currentZone) means null never matches.
        val state = NavigationState(
            amenities = listOf(
                amenity(1, zone = "secure"),
                amenity(2, zone = null)
            ),
            currentZone = "secure"
        )
        val result = filteredAmenities(state)
        assertEquals(1, result.size)
        assertEquals(1, result[0].id)
    }

}
