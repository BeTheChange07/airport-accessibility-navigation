package com.example.se6387map

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Account view: edit display name, sign out, delete account.
 * Saved filters and accessibility prefs are read-only here -- the
 * wheelchair toggle on the main screen still drives that pref.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountSettingsScreen(
    authViewModel: AuthViewModel,
    onClose: () -> Unit,
    onShowReports: () -> Unit = {},
    // Live state of the wheelchair filter from NavigationViewModel.
    // The host wires it so this screen stays in sync with the main map's
    // Filters chip; toggling here flips both at once.
    accessibilityModeOn: Boolean = false,
    onAccessibilityToggle: (Boolean) -> Unit = {},
) {
    val state by authViewModel.state.collectAsState()
    val user = state.user
    var showDeleteConfirm by remember { mutableStateOf(false) }
    var nameField by remember(user?.id) { mutableStateOf(user?.name ?: "") }

    // Once the VM reports logged-out, dismiss.
    LaunchedEffect(user) {
        if (user == null) onClose()
    }

    ModalBottomSheet(onDismissRequest = onClose) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(24.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Text("Account", style = MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.height(4.dp))
            Text(
                "Signed in as ${user?.username ?: ""}",
                color = Color.Gray
            )

            Spacer(Modifier.height(20.dp))
            OutlinedTextField(
                value = nameField,
                onValueChange = { nameField = it },
                label = { Text("Display name") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
            Button(
                onClick = { authViewModel.updateName(nameField.ifBlank { null }) },
                modifier = Modifier.fillMaxWidth()
            ) { Text("Save name") }

            Spacer(Modifier.height(24.dp))
            Text("Preferences", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                Switch(
                    checked = accessibilityModeOn,
                    onCheckedChange = { onAccessibilityToggle(it) }
                )
                Spacer(Modifier.width(12.dp))
                Column {
                    Text("Wheelchair-only filter")
                    Text(
                        "Hides amenities marked 'no'. Synced to your account.",
                        color = Color.Gray, fontSize = 12.sp
                    )
                }
            }
            user?.accessibility_prefs?.takeIf { it.size() > 0 }?.let {
                Spacer(Modifier.height(6.dp))
                Text("Saved on server: $it", color = Color.Gray, fontSize = 12.sp)
            }

            Spacer(Modifier.height(24.dp))
            Text("Saved filters", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(4.dp))
            val filtersText = user?.filters?.takeIf { it.size() > 0 }?.toString()
                ?: "No saved filters."
            Text(filtersText, color = Color.Gray)

            state.error?.let {
                Spacer(Modifier.height(12.dp))
                Text(it, color = MaterialTheme.colorScheme.error)
            }

            Spacer(Modifier.height(20.dp))
            Button(
                onClick = onShowReports,
                modifier = Modifier.fillMaxWidth()
            ) { Text("My reports") }

            Spacer(Modifier.height(20.dp))
            OutlinedButton(
                onClick = { authViewModel.logout() },
                modifier = Modifier.fillMaxWidth()
            ) { Text("Sign out") }
            Spacer(Modifier.height(8.dp))
            OutlinedButton(
                onClick = { showDeleteConfirm = true },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.Red)
            ) { Text("Delete account") }
            Spacer(Modifier.height(16.dp))
        }
    }

    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            title = { Text("Delete account?") },
            text = {
                Text(
                    "This permanently deletes ${user?.username} and all your reports."
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    showDeleteConfirm = false
                    authViewModel.deleteAccount()
                }) { Text("Delete", color = Color.Red) }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }) { Text("Cancel") }
            }
        )
    }
}
