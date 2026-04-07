// Data classes mirror the Flask JSON exactly, so they keep snake_case
// field names. Suppress the Kotlin style checks for this file rather
// than renaming + annotating every field with @SerializedName.
@file:Suppress("PropertyName", "ConstructorParameterNaming")

package com.example.se6387map

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.GET
import retrofit2.http.Query
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

// Data classes matching your Flask API responses
data class RouteResponse(
    val from_node: Int,
    val to_node: Int,
    val total_distance: Double,
    val num_waypoints: Int,
    val waypoints: List<Waypoint>,
    // Present only in route-to-amenity responses
    val amenity_type: String? = null,
    val destination_name: String? = null
)

data class Waypoint(
    val seq: Int,
    val node_id: Int,
    val latitude: Double,
    val longitude: Double,
    val label: String,
    val node_type: String,
    val direction: String?,
    val instruction: String,
    val distance_to_next: Double,
    val bearing_to_next: Double?,
    val cardinal_direction: String?,
    val distance_meters: Double?
)

data class NearestNodeResponse(
    val node_id: Int,
    val latitude: Double,
    val longitude: Double,
    val label: String,
    val node_type: String,
    val zone: String? = null
)

data class NodesResponse(
    val nodes: List<NodeItem>
)

data class NodeItem(
    val id: Int,
    val latitude: Double,
    val longitude: Double,
    val label: String,
    val node_type: String
)

data class AmenityTypesResponse(
    val amenity_types: List<String>
)

data class Amenity(
    val id: Int,
    val nodeid: Int,
    val name: String,
    val type: String,
    val latitude: Double,
    val longitude: Double,
    val status: String,
    val wheelchairaccessible: String?,
    val has_accessible_unit: Boolean?,
    val zone: String? = null
)

data class RandomNodeResponse(
    val node_id: Int,
    val latitude: Double,
    val longitude: Double,
    val zone: String
)

data class AmenitiesResponse(
    val amenities: List<Amenity>
)

// Retrofit API interface
interface NavigationApiService {

    @GET("/api/route")
    suspend fun getRoute(
        @Query("from_node") fromNode: Int,
        @Query("to_node") toNode: Int
    ): RouteResponse

    @GET("/api/nearest")
    suspend fun getNearestNode(
        @Query("lat") lat: Double,
        @Query("lng") lng: Double,
        @Query("zone") zone: String? = null
    ): NearestNodeResponse

    // Kept for ad-hoc debugging / future use — don't flag as unused.
    @Suppress("unused")
    @GET("/api/nodes")
    suspend fun getNodes(
        @Query("type") type: String? = null
    ): NodesResponse

    @GET("/api/amenity-types")
    suspend fun getAmenityTypes(): AmenityTypesResponse

    @GET("/api/amenities")
    suspend fun getAmenities(): AmenitiesResponse

    @GET("/api/route-to-amenity")
    suspend fun getRouteToAmenity(
        @Query("from_node") fromNode: Int,
        @Query("amenity_type") amenityType: String,
        @Query("accessible") accessible: Boolean? = null
    ): RouteResponse

    @GET("/api/random-node")
    suspend fun getRandomNode(
        @Query("zone") zone: String
    ): RandomNodeResponse
}

// Singleton to create the API client
object NavigationApi {
    // Generated at build time from local.properties by the
    // `generateApiConfig` gradle task. See app/build.gradle.kts.
    private val BASE_URL = ApiConfig.BASE_URL

    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    val service: NavigationApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(NavigationApiService::class.java)
    }
}
