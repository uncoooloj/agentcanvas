package com.example.orders

import io.ktor.server.routing.*
import com.example.domain.Order as DomainOrder

data class OrderDto(val id: String)
sealed interface ScreenState

fun DomainOrder.toDto(): OrderDto {
    return OrderDto(id)
}

interface OrdersApi {
    @GET("/orders/{id}")
    suspend fun fetchOrder(@Path("id") id: String): OrderDto
}

fun Route.ordersRoutes() {
    route("/api") {
        get("/orders") {
            call.respondText("ok")
        }
        post("/orders") {
            call.respondText("created")
        }
    }
}

@Composable
fun OrdersNavHost(navController: NavHostController) {
    NavHost(navController, startDestination = "orders") {
        composable(route = "orders/{id}") {
            OrderScreen()
        }
        navigation(route = "settings", startDestination = "settings/home") {
            composable("settings/home") {
                SettingsScreen()
            }
        }
    }
}

fun render(state: ScreenState) {
    when (state) {
        is ScreenState.Loaded -> Unit
        else -> Unit
    }
}
