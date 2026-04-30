package com.example.se6387map

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
// Mirror MainActivity's pattern: a wildcard material3 import. Some
// Material 3 versions ship ExposedDropdownMenu as a scope-extension that
// the explicit import refuses to resolve, but the wildcard pulls it in
// alongside ExposedDropdownMenuBox.
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * "My Reports" surface.
 *
 * Adaptive: when the user is logged in, shows a submit form on top and
 * the past-reports list below. When the user is a guest, only the form
 * is visible (with a "Sign in to track these" note) since /api/reports/mine
 * requires auth.
 *
 * If [prefilledAmenity] is non-null (e.g. user came in from the amenity
 * detail sheet's "Report a problem" button) the amenity selector is
 * locked to that amenity for the form's lifetime.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ReportsScreen(
    reportsViewModel: ReportsViewModel,
    isLoggedIn: Boolean,
    amenities: List<Amenity>,
    prefilledAmenity: Amenity?,
    onClose: () -> Unit
) {
    val state by reportsViewModel.state.collectAsState()

    LaunchedEffect(isLoggedIn) {
        if (isLoggedIn) reportsViewModel.loadMyReports()
    }

    var amenityChoice by remember(prefilledAmenity?.id) {
        mutableStateOf<Amenity?>(prefilledAmenity)
    }
    var category by remember { mutableStateOf<String?>(null) }
    var description by remember { mutableStateOf("") }
    var rating by remember { mutableStateOf(0) }

    ModalBottomSheet(onDismissRequest = onClose) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = 720.dp)
                .padding(horizontal = 20.dp, vertical = 12.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Text(
                if (isLoggedIn) "My reports" else "Submit a report",
                style = MaterialTheme.typography.headlineSmall
            )
            if (!isLoggedIn) {
                Spacer(Modifier.height(4.dp))
                Text(
                    "Sign in to track and follow up on your reports.",
                    color = Color.Gray, fontSize = 12.sp
                )
            }

            // ---- Submit form ----
            Spacer(Modifier.height(16.dp))
            Text("New report", fontWeight = FontWeight.SemiBold)

            Spacer(Modifier.height(8.dp))
            if (prefilledAmenity != null) {
                Text(
                    "Reporting on: ${prefilledAmenity.name}",
                    fontSize = 14.sp,
                    color = Color.DarkGray
                )
            } else {
                AmenityPicker(
                    amenities = amenities,
                    selected = amenityChoice,
                    onSelect = { amenityChoice = it }
                )
            }

            Spacer(Modifier.height(8.dp))
            CategoryPicker(selected = category, onSelect = { category = it })

            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = description,
                onValueChange = { description = it },
                label = { Text("What happened? (optional)") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 2, maxLines = 4
            )

            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Rating (optional)", fontSize = 13.sp, color = Color.Gray)
                Spacer(Modifier.width(8.dp))
                StarRating(rating = rating, onChange = { rating = it })
            }

            state.error?.let {
                Spacer(Modifier.height(8.dp))
                Text(it, color = MaterialTheme.colorScheme.error, fontSize = 12.sp)
            }
            state.info?.let {
                Spacer(Modifier.height(8.dp))
                Text(it, color = Color(0xFF1B7F3A), fontSize = 12.sp)
            }

            Spacer(Modifier.height(12.dp))
            val targetAmenity = prefilledAmenity ?: amenityChoice
            Button(
                onClick = {
                    val a = targetAmenity ?: return@Button
                    val cat = category ?: return@Button
                    reportsViewModel.submit(
                        SubmitReportRequest(
                            amenity_id = a.id,
                            category = cat,
                            description = description.trim().ifBlank { null },
                            rating = rating.takeIf { it > 0 },
                        )
                    ) {
                        // Reset the form on success.
                        if (prefilledAmenity == null) amenityChoice = null
                        category = null
                        description = ""
                        rating = 0
                    }
                },
                enabled = !state.submitting && targetAmenity != null && category != null,
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(if (state.submitting) "Submitting…" else "Submit report")
            }
            Spacer(Modifier.height(8.dp))
            TextButton(onClick = onClose, modifier = Modifier.fillMaxWidth()) {
                Text("Close")
            }

            // ---- Past reports list ----
            if (isLoggedIn) {
                Spacer(Modifier.height(16.dp))
                HorizontalDivider()
                Spacer(Modifier.height(12.dp))
                Text("Past reports", fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                when {
                    state.isLoading -> Text("Loading…", color = Color.Gray)
                    state.reports.isEmpty() -> Text(
                        "No reports yet.", color = Color.Gray, fontSize = 13.sp
                    )
                    else -> state.reports.forEach { ReportRow(it) }
                }
            }

            Spacer(Modifier.height(24.dp))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AmenityPicker(
    amenities: List<Amenity>,
    selected: Amenity?,
    onSelect: (Amenity) -> Unit
) {
    var expanded by remember { mutableStateOf(false) }
    ExposedDropdownMenuBox(
        expanded = expanded,
        onExpandedChange = { expanded = !expanded }
    ) {
        OutlinedTextField(
            value = selected?.let { "${it.name} (${it.type})" } ?: "Pick an amenity…",
            onValueChange = {},
            readOnly = true,
            label = { Text("Amenity") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(MenuAnchorType.PrimaryNotEditable)
        )
        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false }
        ) {
            amenities.sortedBy { it.name }.forEach { a ->
                DropdownMenuItem(
                    text = { Text("${a.name} · ${a.type}") },
                    onClick = {
                        onSelect(a)
                        expanded = false
                    }
                )
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CategoryPicker(selected: String?, onSelect: (String) -> Unit) {
    var expanded by remember { mutableStateOf(false) }
    val display = REPORT_CATEGORIES.firstOrNull { it.first == selected }?.second
        ?: "Pick a category…"
    ExposedDropdownMenuBox(
        expanded = expanded,
        onExpandedChange = { expanded = !expanded }
    ) {
        OutlinedTextField(
            value = display,
            onValueChange = {},
            readOnly = true,
            label = { Text("Category") },
            trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = expanded) },
            modifier = Modifier
                .fillMaxWidth()
                .menuAnchor(MenuAnchorType.PrimaryNotEditable)
        )
        ExposedDropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false }
        ) {
            REPORT_CATEGORIES.forEach { (key, label) ->
                DropdownMenuItem(
                    text = { Text(label) },
                    onClick = {
                        onSelect(key)
                        expanded = false
                    }
                )
            }
        }
    }
}

@Composable
private fun StarRating(rating: Int, onChange: (Int) -> Unit) {
    Row {
        for (i in 1..5) {
            val filled = i <= rating
            Text(
                text = if (filled) "★" else "☆",
                fontSize = 22.sp,
                color = if (filled) Color(0xFFF9A825) else Color.Gray,
                modifier = Modifier
                    .padding(horizontal = 2.dp)
                    .clickable {
                        // Tapping the same star clears the rating.
                        onChange(if (rating == i) 0 else i)
                    }
            )
        }
    }
}

@Composable
private fun ReportRow(report: UserReport) {
    val statusColor = when (report.status) {
        "resolved"    -> Color(0xFF1B7F3A)
        "in_progress" -> Color(0xFFB45309)
        "dismissed"   -> Color.Gray
        else          -> Color(0xFF1A73E8)   // pending
    }
    val categoryLabel = REPORT_CATEGORIES
        .firstOrNull { it.first == report.category }?.second ?: report.category
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 6.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                modifier = Modifier
                    .size(8.dp)
                    .background(statusColor, CircleShape)
            )
            Spacer(Modifier.width(8.dp))
            Text(
                "$categoryLabel · ${report.amenity_name ?: "amenity #${report.amenity_id}"}",
                fontSize = 14.sp, fontWeight = FontWeight.Medium,
                modifier = Modifier.weight(1f)
            )
            Text(
                report.status.replace('_', ' '),
                color = statusColor, fontSize = 12.sp, fontWeight = FontWeight.SemiBold
            )
        }
        report.description?.takeIf { it.isNotBlank() }?.let {
            Text(it, fontSize = 13.sp, color = Color.DarkGray,
                modifier = Modifier.padding(start = 16.dp, top = 2.dp))
        }
        report.created_at?.let {
            Text(it, fontSize = 11.sp, color = Color.Gray,
                modifier = Modifier.padding(start = 16.dp, top = 2.dp))
        }
    }
    HorizontalDivider()
}

