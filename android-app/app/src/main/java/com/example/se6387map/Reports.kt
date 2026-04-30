@file:Suppress("PropertyName", "ConstructorParameterNaming")

package com.example.se6387map

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

// User-facing labels paired with the backend category enum. Keep keys
// in sync with REPORT_ALLOWED_CATEGORIES in flask-api/app.py.
val REPORT_CATEGORIES: List<Pair<String, String>> = listOf(
    "out_of_order"  to "Out of order",
    "cleanliness"   to "Cleanliness",
    "accessibility" to "Accessibility issue",
    "wait_time"     to "Long wait",
    "other"         to "Other",
)

data class ReportsState(
    val isLoading: Boolean = false,
    val submitting: Boolean = false,
    val reports: List<UserReport> = emptyList(),
    val error: String? = null,
    val info: String? = null,
)

class ReportsViewModel(app: Application) : AndroidViewModel(app) {
    private val _state = MutableStateFlow(ReportsState())
    val state: StateFlow<ReportsState> = _state

    fun loadMyReports() {
        if (AuthTokenHolder.token.isNullOrEmpty()) return  // guest: nothing to load
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val r = AuthApi.service.listMyReports()
                _state.value = _state.value.copy(isLoading = false, reports = r.reports)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = formatError(e, "Failed to load reports")
                )
            }
        }
    }

    fun submit(request: SubmitReportRequest, onSuccess: () -> Unit) {
        _state.value = _state.value.copy(submitting = true, error = null, info = null)
        viewModelScope.launch {
            try {
                AuthApi.service.submitReport(request)
                _state.value = _state.value.copy(
                    submitting = false,
                    info = "Report submitted. Thanks!",
                )
                onSuccess()
                // Refresh the My Reports list so the new entry appears.
                loadMyReports()
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    submitting = false,
                    error = formatError(e, "Submit failed"),
                )
            }
        }
    }

    fun clearMessages() {
        _state.value = _state.value.copy(error = null, info = null)
    }

    private fun formatError(e: Exception, fallback: String): String {
        if (e is retrofit2.HttpException) {
            return try {
                val body = e.response()?.errorBody()?.string()
                if (!body.isNullOrEmpty()) body else "${e.code()} $fallback"
            } catch (_: Exception) { "${e.code()} $fallback" }
        }
        return e.message ?: fallback
    }
}
