import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// A website the user logged in to in the app. The login itself lives in the WebView cookie store.
class Site {
  Site({required this.name, required this.url, required this.domains, this.readOnly = false});

  final String name;
  final String url;
  final List<String> domains;
  final bool readOnly;

  Map<String, dynamic> toJson() => {'name': name, 'url': url, 'domains': domains, 'readOnly': readOnly};

  factory Site.fromJson(Map<String, dynamic> j) => Site(
        name: j['name'] as String,
        url: j['url'] as String,
        domains: (j['domains'] as List).cast<String>(),
        readOnly: j['readOnly'] == true,
      );

  /// 'https://www.linkedin.com/feed' -> name 'linkedin.com', domains ['linkedin.com'].
  factory Site.fromUrl(String url, {bool readOnly = false}) {
    final host = Uri.parse(url).host.toLowerCase();
    final base = baseDomain(host);
    return Site(name: base, url: url, domains: [base], readOnly: readOnly);
  }
}

String baseDomain(String host) {
  final parts = host.split('.');
  const second = {'co', 'com', 'org', 'net', 'ac', 'gov'};
  if (parts.length >= 3 && parts.last.length == 2 && second.contains(parts[parts.length - 2])) {
    return parts.sublist(parts.length - 3).join('.');
  }
  return parts.length >= 2 ? parts.sublist(parts.length - 2).join('.') : host;
}

bool hostAllowed(String host, List<String> domains) {
  host = host.toLowerCase();
  return domains.any((d) => host == d || host.endsWith('.$d'));
}

/// Pairing with a relay: where it is and the shared secret.
class Pairing {
  Pairing(this.relay, this.token);

  final String relay; // ws(s)://host/phone
  final String token;

  /// Accepts `assertify://pair?relay=wss://host/phone&token=...`.
  static Pairing? parse(String link) {
    final uri = Uri.tryParse(link.trim());
    if (uri == null) return null;
    final relay = uri.queryParameters['relay'];
    final token = uri.queryParameters['token'];
    if (relay == null || token == null || token.isEmpty) return null;
    final r = Uri.tryParse(relay);
    if (r == null || !(r.scheme == 'ws' || r.scheme == 'wss')) return null;
    return Pairing(relay, token);
  }
}

class Store {
  static const _secure = FlutterSecureStorage();

  static Future<List<Site>> sites() async {
    final p = await SharedPreferences.getInstance();
    final raw = p.getString('sites');
    if (raw == null) return [];
    return (jsonDecode(raw) as List).map((e) => Site.fromJson(e as Map<String, dynamic>)).toList();
  }

  static Future<void> saveSites(List<Site> sites) async {
    final p = await SharedPreferences.getInstance();
    await p.setString('sites', jsonEncode(sites.map((s) => s.toJson()).toList()));
  }

  static Future<Pairing?> pairing() async {
    final relay = await _secure.read(key: 'relay');
    final token = await _secure.read(key: 'token');
    return relay == null || token == null ? null : Pairing(relay, token);
  }

  static Future<void> savePairing(Pairing? p) async {
    if (p == null) {
      await _secure.delete(key: 'relay');
      await _secure.delete(key: 'token');
    } else {
      await _secure.write(key: 'relay', value: p.relay);
      await _secure.write(key: 'token', value: p.token);
    }
  }
}
