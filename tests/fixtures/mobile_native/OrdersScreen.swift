import SwiftUI
@testable import CheckoutApp

struct OrdersScreen: View {
    var body: some View {
        NavigationStack {
            NavigationLink("https://example.com/orders", destination: OrderDetailView(orderID: "42"))
        }
        .navigationDestination(for: Route.self) { route in
            OrderDetailView(orderID: route.id)
        }
    }

    func refresh() async {
        if Task.isCancelled {
            return
        } else {
            trackOpen()
        }
    }
}

extension OrdersScreen {
    func trackOpen() {
        Analytics.shared.track("orders")
    }
}

struct OrderDetailView: View {
    let orderID: String

    var body: some View {
        Text(orderID)
    }
}

enum Route {
    case order(id: String)
}
