// Snake_case fields match the Flask JSON; suppress Kotlin naming checks.
@file:Suppress("PropertyName", "ConstructorParameterNaming")

package com.example.se6387map

import android.app.Application
import android.content.Context
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.google.gson.JsonObject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import java.util.concurrent.TimeUnit

// ---------------------------------------------------------------
// Token holder + API client
// ---------------------------------------------------------------
//
// Shared mutable holder so the OkHttp interceptor can stamp
// Authorization on every authed request without each call site
// supplying it explicitly. Backed on disk by AuthStore.
internal object AuthTokenHolder {
    @Volatile var token: String? = null
}

data class User(
    val id: Int,
    val username: String,
    val name: String?,
    val accessibility_prefs: JsonObject?,
    val filters: JsonObject?,
    val profile: JsonObject?,
    val created_at: String?
)

data class RegisterRequest(
    val username: String,
    val password: String,
    val name: String? = null,
    val accessibility_prefs: JsonObject? = null,
    val filters: JsonObject? = null,
    val profile: JsonObject? = null
)

data class LoginRequest(val username: String, val password: String)

data class AuthResponse(
    val token: String,
    val expires_at: String,
    val user: User
)

data class MeResponse(val user: User)

data class UpdateMeRequest(
    val name: String? = null,
    val accessibility_prefs: JsonObject? = null,
    val filters: JsonObject? = null,
    val profile: JsonObject? = null
)

// ---------------------------------------------------------------
// UC3 — User reports (data classes; endpoints below are part of
// AuthApiService so they share the bearer-token interceptor).
// ---------------------------------------------------------------
data class UserReport(
    val id: Int,
    val amenity_id: Int,
    val amenity_name: String? = null,
    val amenity_type: String? = null,
    val user_id: Int? = null,
    val username: String? = null,
    val category: String,
    val description: String? = null,
    val rating: Int? = null,
    val status: String,
    val created_at: String? = null,
    val resolved_at: String? = null
)

data class SubmitReportRequest(
    val amenity_id: Int,
    val category: String,
    val description: String? = null,
    val rating: Int? = null
)

data class ReportEnvelope(val report: UserReport)
data class MyReportsResponse(val reports: List<UserReport>)
data class ReportStatusUpdate(val status: String)

interface AuthApiService {
    @POST("/api/auth/register")
    suspend fun register(@Body body: RegisterRequest): AuthResponse

    @POST("/api/auth/login")
    suspend fun login(@Body body: LoginRequest): AuthResponse

    @POST("/api/auth/logout")
    suspend fun logout(): Map<String, String>

    @GET("/api/me")
    suspend fun getMe(): MeResponse

    @PUT("/api/me")
    suspend fun updateMe(@Body body: UpdateMeRequest): MeResponse

    @DELETE("/api/me")
    suspend fun deleteMe(): Map<String, String>

    // UC3 endpoints
    @POST("/api/reports")
    suspend fun submitReport(@Body body: SubmitReportRequest): ReportEnvelope

    @GET("/api/reports/mine")
    suspend fun listMyReports(): MyReportsResponse
}

object AuthApi {
    private val client = OkHttpClient.Builder()
        .addInterceptor { chain ->
            val req = chain.request()
            val t = AuthTokenHolder.token
            val out = if (t.isNullOrEmpty()) req
                else req.newBuilder().addHeader("Authorization", "Bearer $t").build()
            chain.proceed(out)
        }
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    val service: AuthApiService by lazy {
        Retrofit.Builder()
            .baseUrl(ApiConfig.BASE_URL)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(AuthApiService::class.java)
    }
}

// ---------------------------------------------------------------
// On-device token persistence
// ---------------------------------------------------------------
internal class AuthStore(context: Context) {
    private val prefs = context.getSharedPreferences("auth", Context.MODE_PRIVATE)

    var token: String?
        get() = prefs.getString("token", null)
        set(value) { prefs.edit().putString("token", value).apply() }

    fun clear() { prefs.edit().clear().apply() }
}

// ---------------------------------------------------------------
// AuthViewModel
// ---------------------------------------------------------------
data class AuthState(
    val isLoading: Boolean = false,
    val user: User? = null,
    val token: String? = null,
    val error: String? = null
)

class AuthViewModel(app: Application) : AndroidViewModel(app) {
    private val store = AuthStore(app)
    private val _state = MutableStateFlow(AuthState())
    val state: StateFlow<AuthState> = _state

    init {
        // Re-hydrate token from disk and verify it still works.
        val savedToken = store.token
        if (!savedToken.isNullOrEmpty()) {
            AuthTokenHolder.token = savedToken
            viewModelScope.launch {
                try {
                    val me = AuthApi.service.getMe()
                    _state.value = _state.value.copy(user = me.user, token = savedToken)
                } catch (_: Exception) {
                    // Token is stale or backend unreachable; clear and stay logged out.
                    AuthTokenHolder.token = null
                    store.clear()
                    _state.value = AuthState()
                }
            }
        }
    }

    val isLoggedIn: Boolean get() = _state.value.user != null

    fun login(username: String, password: String) {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val resp = AuthApi.service.login(LoginRequest(username, password))
                AuthTokenHolder.token = resp.token
                store.token = resp.token
                _state.value = AuthState(user = resp.user, token = resp.token)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = formatHttpError(e, "Login failed")
                )
            }
        }
    }

    fun register(username: String, password: String, name: String?) {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val resp = AuthApi.service.register(
                    RegisterRequest(username, password, name)
                )
                AuthTokenHolder.token = resp.token
                store.token = resp.token
                _state.value = AuthState(user = resp.user, token = resp.token)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = formatHttpError(e, "Register failed")
                )
            }
        }
    }

    fun logout() {
        viewModelScope.launch {
            try { AuthApi.service.logout() } catch (_: Exception) { /* still clear locally */ }
            AuthTokenHolder.token = null
            store.clear()
            _state.value = AuthState()
        }
    }

    fun deleteAccount() {
        viewModelScope.launch {
            try { AuthApi.service.deleteMe() } catch (_: Exception) { /* still clear locally */ }
            AuthTokenHolder.token = null
            store.clear()
            _state.value = AuthState()
        }
    }

    fun updateName(newName: String?) {
        viewModelScope.launch {
            try {
                val r = AuthApi.service.updateMe(UpdateMeRequest(name = newName))
                _state.value = _state.value.copy(user = r.user, error = null)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = formatHttpError(e, "Update failed"))
            }
        }
    }

    /** Best-effort persist of the wheelchair-only preference. No-op when logged out. */
    fun persistWheelchairPref(enabled: Boolean) {
        if (!isLoggedIn) return
        val prefs = JsonObject().apply { addProperty("wheelchair_only", enabled) }
        viewModelScope.launch {
            try {
                val r = AuthApi.service.updateMe(UpdateMeRequest(accessibility_prefs = prefs))
                _state.value = _state.value.copy(user = r.user)
            } catch (_: Exception) {
                /* swallow -- best-effort persistence */
            }
        }
    }

    fun clearError() {
        _state.value = _state.value.copy(error = null)
    }

    private fun formatHttpError(e: Exception, fallback: String): String {
        if (e is retrofit2.HttpException) {
            return try {
                val body = e.response()?.errorBody()?.string()
                if (!body.isNullOrEmpty()) body else "${e.code()} $fallback"
            } catch (_: Exception) { "${e.code()} $fallback" }
        }
        return e.message ?: fallback
    }
}
