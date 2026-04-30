package com.example.se6387map

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp

/**
 * Combined login + register sheet. Toggle at the bottom flips between modes.
 * Auto-dismisses once the AuthViewModel reports a logged-in user.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LoginScreen(
    authViewModel: AuthViewModel,
    onClose: () -> Unit
) {
    val state by authViewModel.state.collectAsState()
    var isRegistering by remember { mutableStateOf(false) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }

    LaunchedEffect(state.user) {
        if (state.user != null) onClose()
    }

    ModalBottomSheet(onDismissRequest = onClose) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(24.dp)
                .verticalScroll(rememberScrollState())
        ) {
            Text(
                if (isRegistering) "Create account" else "Sign in",
                style = MaterialTheme.typography.headlineSmall
            )
            Spacer(Modifier.height(16.dp))

            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                label = { Text("Username") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(Modifier.height(8.dp))
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Password") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                modifier = Modifier.fillMaxWidth()
            )
            if (isRegistering) {
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Display name (optional)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )
            }

            state.error?.let {
                Spacer(Modifier.height(8.dp))
                Text(it, color = MaterialTheme.colorScheme.error)
            }

            Spacer(Modifier.height(16.dp))
            Button(
                onClick = {
                    authViewModel.clearError()
                    if (isRegistering) {
                        authViewModel.register(
                            username.trim(), password, name.ifBlank { null }
                        )
                    } else {
                        authViewModel.login(username.trim(), password)
                    }
                },
                // 6-char minimum only applies when creating a new account.
                // Existing accounts (e.g. seeded demo users with shorter
                // legacy passwords) must still be able to sign in.
                enabled = !state.isLoading
                    && username.isNotBlank()
                    && password.isNotEmpty()
                    && (!isRegistering || password.length >= 6),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    when {
                        state.isLoading -> "Working…"
                        isRegistering -> "Create account"
                        else -> "Sign in"
                    }
                )
            }

            Spacer(Modifier.height(8.dp))
            TextButton(onClick = {
                isRegistering = !isRegistering
                authViewModel.clearError()
            }) {
                Text(
                    if (isRegistering)
                        "Already have an account? Sign in"
                    else
                        "Need an account? Register"
                )
            }
            TextButton(onClick = onClose) { Text("Continue as guest") }
            Spacer(Modifier.height(16.dp))
        }
    }
}
