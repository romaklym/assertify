import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'package:web_socket_channel/io.dart';

import 'store.dart';

/// One page the agent is working in: a WebView with no window, sharing the app's cookies.
class HiddenPage {
  HiddenPage(this.site);

  final Site site;
  HeadlessInAppWebView? view;
  InAppWebViewController? c;
  final events = <String>[];
  bool loading = false;

  Future<void> start(String url) async {
    final ready = Completer<void>();
    view = HeadlessInAppWebView(
      initialSize: const Size(390, 844),
      initialUrlRequest: URLRequest(url: WebUri(url)),
      initialSettings: InAppWebViewSettings(
        javaScriptEnabled: true,
        useShouldOverrideUrlLoading: true,
        mediaPlaybackRequiresUserGesture: true,
        javaScriptCanOpenWindowsAutomatically: false,
        supportMultipleWindows: false,
        isInspectable: kDebugMode,
      ),
      onWebViewCreated: (c) => this.c = c,
      onLoadStart: (_, _) => loading = true,
      onLoadStop: (_, _) {
        loading = false;
        if (!ready.isCompleted) ready.complete();
      },
      onReceivedError: (_, req, err) {
        if (req.isForMainFrame == true) {
          loading = false;
          if (!ready.isCompleted) ready.complete();
        }
      },
      // Stay on the site's own domains, like the desktop domain guard.
      shouldOverrideUrlLoading: (_, action) async {
        final u = action.request.url;
        if (u == null || action.isForMainFrame == false) return NavigationActionPolicy.ALLOW;
        if (u.scheme != 'http' && u.scheme != 'https') {
          if (u.scheme == 'about' || u.scheme == 'data' || u.scheme == 'blob') return NavigationActionPolicy.ALLOW;
          events.add('Blocked a link to a ${u.scheme}: address.');
          return NavigationActionPolicy.CANCEL;
        }
        if (!hostAllowed(u.host, site.domains)) {
          events.add('Blocked: ${u.host} is outside this site\'s allowed domains (${site.domains.join(', ')}).');
          return NavigationActionPolicy.CANCEL;
        }
        return NavigationActionPolicy.ALLOW;
      },
      // alert/confirm/prompt: never leave the page stuck; cancel confirms and report them.
      onJsAlert: (_, req) async {
        events.add('The page showed an alert: "${_short(req.message)}". It was closed.');
        return JsAlertResponse(handledByClient: true, action: JsAlertResponseAction.CONFIRM);
      },
      onJsConfirm: (_, req) async {
        events.add('The page asked "${_short(req.message)}". It was dismissed (Cancel).');
        return JsConfirmResponse(handledByClient: true, action: JsConfirmResponseAction.CANCEL);
      },
      onJsPrompt: (_, req) async {
        events.add('The page showed a prompt: "${_short(req.message)}". It was dismissed.');
        return JsPromptResponse(handledByClient: true, action: JsPromptResponseAction.CANCEL);
      },
    );
    await view!.run();
    await ready.future.timeout(const Duration(seconds: 40), onTimeout: () {});
  }

  Future<void> wait(int ms) async {
    final end = DateTime.now().add(Duration(milliseconds: ms));
    await Future.delayed(const Duration(milliseconds: 250));
    while (DateTime.now().isBefore(end) && (loading || await c!.isLoading())) {
      await Future.delayed(const Duration(milliseconds: 150));
    }
    await Future.delayed(const Duration(milliseconds: 300)); // let scripts render
  }

  Future<dynamic> eval(String fn, dynamic arg) async {
    final r = await c!.callAsyncJavaScript(
      functionBody: 'return await ($fn)(arg);',
      arguments: {'arg': arg},
    );
    if (r == null) return null;
    if (r.error != null) throw Exception('Page script failed: ${r.error}');
    return r.value;
  }

  Future<void> close() async {
    await view?.dispose();
    view = null;
  }

  static String _short(String? s) => (s ?? '').length > 200 ? '${s!.substring(0, 200)}…' : (s ?? '');
}

enum LinkState { off, connecting, online, refused }

/// Keeps the WebSocket to the relay open and runs what the agent asks.
class Agent extends ChangeNotifier {
  Agent(this.sitesFn);

  final Future<List<Site>> Function() sitesFn;
  Pairing? pairing;
  IOWebSocketChannel? _ch;
  StreamSubscription? _sub;
  Timer? _retry;
  Timer? _ping;
  int _backoff = 1;
  LinkState state = LinkState.off;
  String? error;
  final pages = <String, HiddenPage>{};
  final activity = <String>[];

  void log(String s) {
    final t = DateTime.now();
    activity.insert(0, '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}  $s');
    if (activity.length > 100) activity.removeLast();
    notifyListeners();
  }

  Future<void> connect(Pairing? p) async {
    pairing = p;
    await disconnect();
    if (p == null) return;
    _open();
  }

  Future<void> disconnect() async {
    _retry?.cancel();
    _ping?.cancel();
    await _sub?.cancel();
    await _ch?.sink.close();
    _ch = null;
    state = LinkState.off;
    for (final p in pages.values) {
      await p.close();
    }
    pages.clear();
    notifyListeners();
  }

  void _open() async {
    final p = pairing;
    if (p == null) return;
    state = LinkState.connecting;
    notifyListeners();
    try {
      final ws = await WebSocket.connect(p.relay).timeout(const Duration(seconds: 15));
      ws.pingInterval = const Duration(seconds: 20);
      _ch = IOWebSocketChannel(ws);
      final sites = await sitesFn();
      _ch!.sink.add(jsonEncode({
        'type': 'hello',
        'token': p.token,
        'device': Platform.isIOS ? 'iPhone' : 'Android phone',
        'sites': sites.map((s) => s.toJson()).toList(),
      }));
      _sub = _ch!.stream.listen(_onMessage, onDone: _onClosed, onError: (_) => _onClosed());
    } catch (e) {
      error = '$e';
      _schedule();
    }
  }

  void _onClosed() {
    final code = _ch?.closeCode;
    _ch = null;
    _ping?.cancel();
    for (final p in pages.values) {
      p.close();
    }
    pages.clear();
    if (code == 4401) {
      state = LinkState.refused;
      error = 'The relay refused the pairing token. Pair again.';
      notifyListeners();
      return;
    }
    if (code == 4000) {
      state = LinkState.off;
      error = 'Another phone connected to this relay.';
      notifyListeners();
      return;
    }
    _schedule();
  }

  void _schedule() {
    state = LinkState.connecting;
    notifyListeners();
    _retry?.cancel();
    _retry = Timer(Duration(seconds: _backoff), _open);
    _backoff = (_backoff * 2).clamp(1, 30);
  }

  /// Call after sites change so agents see the new list.
  Future<void> sitesChanged() async {
    final sites = await sitesFn();
    _ch?.sink.add(jsonEncode({'type': 'sites', 'sites': sites.map((s) => s.toJson()).toList()}));
  }

  void _onMessage(dynamic raw) async {
    final msg = jsonDecode(raw as String) as Map<String, dynamic>;
    if (msg['type'] == 'welcome') {
      state = LinkState.online;
      error = null;
      _backoff = 1;
      notifyListeners();
      return;
    }
    if (msg['type'] == 'pong' || msg['id'] == null) return;
    final id = msg['id'];
    try {
      final result = await _run(msg['op'] as String, (msg['args'] as Map).cast<String, dynamic>());
      _ch?.sink.add(jsonEncode({'id': id, 'ok': true, 'result': result}));
    } catch (e) {
      _ch?.sink.add(jsonEncode({'id': id, 'ok': false, 'error': e.toString().replaceFirst('Exception: ', '')}));
    }
  }

  HiddenPage _page(String sid) {
    final p = pages[sid];
    if (p == null || p.c == null) throw Exception('That session is not open on the phone anymore.');
    return p;
  }

  Future<dynamic> _run(String op, Map<String, dynamic> a) async {
    final sid = a['sid'] as String?;
    switch (op) {
      case 'open':
        final sites = await sitesFn();
        final site = sites.firstWhere((s) => s.name == a['site'],
            orElse: () => throw Exception('No login for ${a['site']} in the app.'));
        final url = (a['url'] as String?) ?? site.url;
        if (!hostAllowed(Uri.parse(url).host, site.domains)) {
          throw Exception('Blocked: $url is outside ${site.name}\'s allowed domains.');
        }
        final page = HiddenPage(site);
        pages[sid!] = page;
        log('Agent opened ${site.name}');
        await page.start(url);
        return true;
      case 'close':
        await pages.remove(sid)?.close();
        log('Agent closed a session');
        return true;
      case 'goto':
        final p = _page(sid!);
        final url = a['url'] as String;
        if (!hostAllowed(Uri.parse(url).host, p.site.domains)) {
          throw Exception('Blocked: $url is outside ${p.site.name}\'s allowed domains.');
        }
        p.loading = true;
        await p.c!.loadUrl(urlRequest: URLRequest(url: WebUri(url)));
        log('Agent went to ${Uri.parse(url).host}${Uri.parse(url).path}');
        return true;
      case 'back':
        await _page(sid!).c!.goBack();
        return true;
      case 'wait':
        await _page(sid!).wait((a['ms'] as num?)?.toInt() ?? 5000);
        return true;
      case 'events':
        final p = _page(sid!);
        final out = List<String>.from(p.events);
        p.events.clear();
        return out;
      case 'state':
        final c = _page(sid!).c!;
        return {'url': (await c.getUrl())?.toString(), 'title': await c.getTitle()};
      case 'eval':
        return _page(sid!).eval(a['fn'] as String, a['arg']);
      case 'screenshot':
        final bytes = await _page(sid!).c!.takeScreenshot(
              screenshotConfiguration:
                  ScreenshotConfiguration(compressFormat: CompressFormat.JPEG, quality: 70),
            );
        if (bytes == null) throw Exception('The phone could not take a screenshot.');
        return base64Encode(bytes);
      default:
        throw Exception('Unknown command $op. Update the Assertify app.');
    }
  }
}
