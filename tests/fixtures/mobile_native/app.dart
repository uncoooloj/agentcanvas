import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

export 'src/details.dart';
part 'home_state.dart';

extension type UserId(String value) {}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return TextButton(
      onPressed: () => Navigator.of(context).pushNamed('/orders'),
      child: const Text('Orders'),
    );
  }
}

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) => const Text('Settings');
}

Future<void> loadOrders(BuildContext context) async {
  if (context.mounted) {
    Navigator.pushReplacementNamed(context, '/orders');
  } else if (DateTime.now().isUtc) {
    Navigator.of(context).pushNamed('/settings');
  } else {
    debugPrint('offline');
  }
}

final appRouter = GoRouter(
  routes: [
    GoRoute(
      name: 'home',
      path: '/home',
      builder: (context, state) => const HomeScreen(),
    ),
  ],
);

final namedRoutes = <String, WidgetBuilder>{
  '/settings': (context) => const SettingsScreen(),
};
