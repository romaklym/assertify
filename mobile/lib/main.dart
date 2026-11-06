import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

import 'agent.dart';
import 'store.dart';

/// Debug/testing: `flutter run --dart-define=PAIR='assertify://pair?relay=...&token=...'`.
const _pairFromBuild = String.fromEnvironment('PAIR');

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AssertifyApp());
}

class AssertifyApp extends StatelessWidget {
  const AssertifyApp({super.key});

  @override
  Widget build(BuildContext context) {
    final seed = const Color(0xFF3B5BDB);
    return MaterialApp(
      title: 'Assertify',
      theme: ThemeData(colorSchemeSeed: seed, useMaterial3: true),
      darkTheme: ThemeData(colorSchemeSeed: seed, brightness: Brightness.dark, useMaterial3: true),
      home: const Home(),
    );
  }
}

class Home extends StatefulWidget {
  const Home({super.key});

  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> with WidgetsBindingObserver {
  List<Site> sites = [];
  late final Agent agent = Agent(() async => sites);
  StreamSubscription? _links;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    agent.addListener(() => mounted ? setState(() {}) : null);
    _load();
  }

  Future<void> _load() async {
    sites = await Store.sites();
    var p = await Store.pairing();
    if (p == null && _pairFromBuild.isNotEmpty) {
      p = Pairing.parse(_pairFromBuild);
      await Store.savePairing(p);
    }
    setState(() {});
    await agent.connect(p);
    final links = AppLinks();
    _links = links.uriLinkStream.listen((uri) => _pair(uri.toString()));
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    // iOS drops sockets while the app is suspended: reconnect as soon as it's back.
    if (s == AppLifecycleState.resumed && agent.state != LinkState.online && agent.pairing != null) {
      agent.connect(agent.pairing);
    }
  }

  @override
  void dispose() {
    _links?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  Future<void> _pair(String link) async {
    final p = Pairing.parse(link);
    if (p == null) {
      _toast('That isn\'t an Assertify pairing link.');
      return;
    }
    await Store.savePairing(p);
    await agent.connect(p);
    _toast('Paired with ${Uri.parse(p.relay).host}');
  }

  void _toast(String s) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(s)));

  Future<void> _addSite() async {
    final url = await showDialog<String>(context: context, builder: (_) => const _AddSiteDialog());
    if (url == null || !mounted) return;
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => LoginBrowser(url: url, adding: true)));
    final site = Site.fromUrl(url);
    sites = [...sites.where((s) => s.name != site.name), site];
    await Store.saveSites(sites);
    await agent.sitesChanged();
    setState(() {});
  }

  Future<void> _removeSite(Site s) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text('Remove ${s.name}?'),
        content: const Text('Agents won\'t see this site anymore. To sign out completely, also clear its cookies.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Cancel')),
          TextButton(onPressed: () => Navigator.pop(c, true), child: const Text('Remove')),
        ],
      ),
    );
    if (ok != true) return;
    sites = sites.where((x) => x.name != s.name).toList();
    await Store.saveSites(sites);
    await agent.sitesChanged();
    setState(() {});
  }

  Future<void> _pairDialog() async {
    final ctl = TextEditingController();
    final link = await showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Pair with a relay'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Text('Run `assertify relay` on a computer or server and paste the pairing link it prints.'),
          const SizedBox(height: 12),
          TextField(
            controller: ctl,
            decoration: const InputDecoration(hintText: 'assertify://pair?relay=…&token=…'),
            autocorrect: false,
            maxLines: 3,
            minLines: 1,
          ),
        ]),
        actions: [
          if (agent.pairing != null)
            TextButton(onPressed: () => Navigator.pop(c, ''), child: const Text('Unpair')),
          TextButton(
            onPressed: () async {
              final d = await Clipboard.getData('text/plain');
              if (d?.text != null) ctl.text = d!.text!;
            },
            child: const Text('Paste'),
          ),
          FilledButton(onPressed: () => Navigator.pop(c, ctl.text), child: const Text('Pair')),
        ],
      ),
    );
    if (link == null) return;
    if (link.isEmpty) {
      await Store.savePairing(null);
      await agent.connect(null);
      return;
    }
    await _pair(link);
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final (label, color, icon) = switch (agent.state) {
      LinkState.online => ('Agents can use your sites', Colors.green, Icons.check_circle),
      LinkState.connecting => ('Connecting to relay…', Colors.orange, Icons.sync),
      LinkState.refused => ('Pairing refused', t.colorScheme.error, Icons.error),
      LinkState.off => (agent.pairing == null ? 'Not paired' : 'Offline', Colors.grey, Icons.link_off),
    };
    return Scaffold(
      appBar: AppBar(title: const Text('Assertify')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _addSite,
        icon: const Icon(Icons.add),
        label: const Text('Log in to a site'),
      ),
      body: ListView(padding: const EdgeInsets.fromLTRB(16, 8, 16, 96), children: [
        Card(
          child: ListTile(
            leading: Icon(icon, color: color),
            title: Text(label),
            subtitle: Text(agent.pairing == null
                ? 'Pair with a relay so Claude, Codex and other agents can reach this phone.'
                : agent.error ?? '${Uri.parse(agent.pairing!.relay).host} · ${agent.pages.length} open'),
            trailing: TextButton(onPressed: _pairDialog, child: Text(agent.pairing == null ? 'Pair' : 'Change')),
          ),
        ),
        const SizedBox(height: 12),
        Text('Your sites', style: t.textTheme.titleMedium),
        if (sites.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 16),
            child: Text('Log in to a site here once. Agents then use it in a hidden browser on this phone; '
                'your password never leaves the app.'),
          ),
        for (final s in sites)
          Card(
            child: ListTile(
              leading: CircleAvatar(child: Text(s.name.substring(0, 1).toUpperCase())),
              title: Text(s.name),
              subtitle: Text(s.url, maxLines: 1, overflow: TextOverflow.ellipsis),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => LoginBrowser(url: s.url))),
              trailing: IconButton(icon: const Icon(Icons.delete_outline), onPressed: () => _removeSite(s)),
            ),
          ),
        if (agent.activity.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text('Agent activity', style: t.textTheme.titleMedium),
          for (final a in agent.activity.take(20))
            Padding(padding: const EdgeInsets.symmetric(vertical: 2), child: Text(a, style: t.textTheme.bodySmall)),
        ],
      ]),
    );
  }
}

class _AddSiteDialog extends StatefulWidget {
  const _AddSiteDialog();

  @override
  State<_AddSiteDialog> createState() => _AddSiteDialogState();
}

class _AddSiteDialogState extends State<_AddSiteDialog> {
  final ctl = TextEditingController();

  String? get url {
    var s = ctl.text.trim();
    if (s.isEmpty) return null;
    if (!s.contains('://')) s = 'https://$s';
    final u = Uri.tryParse(s);
    return u != null && u.host.contains('.') && (u.scheme == 'https' || u.scheme == 'http') ? s : null;
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Log in to a site'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(
            controller: ctl,
            autofocus: true,
            keyboardType: TextInputType.url,
            autocorrect: false,
            decoration: const InputDecoration(hintText: 'linkedin.com'),
            onChanged: (_) => setState(() {}),
            onSubmitted: (_) => url != null ? Navigator.pop(context, url) : null,
          ),
          const SizedBox(height: 8),
          for (final q in ['linkedin.com', 'x.com', 'github.com'])
            ListTile(dense: true, title: Text(q), onTap: () => Navigator.pop(context, 'https://www.$q/')),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(onPressed: url == null ? null : () => Navigator.pop(context, url), child: const Text('Open')),
        ],
      );
}

/// The visible browser: the user logs in here by hand (passwords, 2FA, CAPTCHAs).
class LoginBrowser extends StatefulWidget {
  const LoginBrowser({super.key, required this.url, this.adding = false});

  final String url;
  final bool adding;

  @override
  State<LoginBrowser> createState() => _LoginBrowserState();
}

class _LoginBrowserState extends State<LoginBrowser> {
  InAppWebViewController? c;
  String host = '';
  double progress = 0;

  @override
  void initState() {
    super.initState();
    host = Uri.parse(widget.url).host;
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: Text(host, style: const TextStyle(fontSize: 16)),
          actions: [
            IconButton(icon: const Icon(Icons.refresh), onPressed: () => c?.reload()),
            TextButton(onPressed: () => Navigator.pop(context), child: Text(widget.adding ? 'Done' : 'Close')),
          ],
          bottom: progress < 1
              ? PreferredSize(preferredSize: const Size.fromHeight(2), child: LinearProgressIndicator(value: progress))
              : null,
        ),
        body: InAppWebView(
          initialUrlRequest: URLRequest(url: WebUri(widget.url)),
          initialSettings: InAppWebViewSettings(javaScriptEnabled: true, allowsBackForwardNavigationGestures: true),
          onWebViewCreated: (c) => this.c = c,
          onProgressChanged: (_, p) => setState(() => progress = p / 100),
          onUpdateVisitedHistory: (_, u, _) => setState(() => host = u?.host ?? host),
        ),
      );
}
