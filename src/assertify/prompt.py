"""A small window where the user types things the agent must never see: the username and
password for a site's browser sign-in box (HTTP Basic/NTLM), and whether to trust its certificate."""

from __future__ import annotations

import asyncio
import html
import string

FORM = string.Template("""<!doctype html><html><head><meta charset="utf-8"><title>Assertify: browser sign-in</title>
<style>
 body { font: 15px -apple-system, system-ui, sans-serif; margin: 32px auto; max-width: 440px; color: #222; }
 h1 { font-size: 19px; margin: 0 0 6px; } p { color: #555; margin: 0 0 18px; line-height: 1.4; }
 label { display: block; margin: 14px 0 4px; font-weight: 600; }
 input[type=text], input[type=password] { width: 100%; padding: 8px; font-size: 15px; box-sizing: border-box; }
 .check { display: flex; gap: 8px; align-items: flex-start; font-weight: 400; margin-top: 18px; }
 .warn { color: #8a5300; font-size: 13px; margin: 4px 0 0 24px; }
 .buttons { margin-top: 24px; display: flex; gap: 10px; }
 button { padding: 8px 18px; font-size: 15px; }
</style></head><body>
<h1>Browser settings for $site</h1>
<p>Only for sites that show the browser's own sign-in box, or use a certificate your browser doesn't trust
(common for company intranets and devices). The AI agent can't see what you type here; it's saved
encrypted with the login <b>$profile</b>.</p>
<form id="f">
 <label for="u">Username</label><input type="text" id="u" autocomplete="off" value="$user">
 <label for="p">Password</label><input type="password" id="p" autocomplete="off"
   placeholder="$placeholder">
 <label class="check"><input type="checkbox" id="c" $checked> Trust this site's certificate even if it
   isn't valid (self-signed)</label>
 <div class="warn">Only tick this for a site you control or your company runs. It turns off the check that
   stops someone pretending to be the site.</div>
 <div class="buttons"><button type="submit">Save</button><button type="button" id="x">Cancel</button></div>
</form>
<script>
 document.getElementById('f').onsubmit = (e) => { e.preventDefault(); window.__done = {
   save: true, user: document.getElementById('u').value, password: document.getElementById('p').value,
   trust: document.getElementById('c').checked }; };
 document.getElementById('x').onclick = () => { window.__done = {save: false}; };
</script></body></html>""")


async def ask(pw, launch, profile: str, site: str, user: str, has_password: bool, trusted: bool) -> dict | None:
    """Show the form and wait for the user. Returns their answers, or None if they cancelled or closed it."""
    browser = await launch(pw, headless=False)
    page = await browser.new_page(viewport={"width": 560, "height": 560})
    try:
        await page.set_content(
            FORM.substitute(
                site=html.escape(site),
                profile=html.escape(profile),
                user=html.escape(user, quote=True),
                placeholder="(unchanged, leave empty to keep it)" if has_password else "",
                checked="checked" if trusted else "",
            )
        )
        await page.bring_to_front()
        closed = asyncio.get_running_loop().create_future()
        page.on("close", lambda _: closed.done() or closed.set_result(None))
        answer = asyncio.ensure_future(page.wait_for_function("window.__done", timeout=600_000))
        done, _ = await asyncio.wait([answer, closed], return_when=asyncio.FIRST_COMPLETED)
        if answer not in done:
            answer.cancel()
            return None
        result = await (await answer).json_value()
        return result if result.get("save") else None
    except Exception as e:
        if page.is_closed() or not browser.is_connected():  # the user closed the window mid-way
            return None
        raise RuntimeError(f"The settings window failed: {str(e).splitlines()[0]}") from e
    finally:
        try:
            await browser.close()
        except Exception:
            pass
