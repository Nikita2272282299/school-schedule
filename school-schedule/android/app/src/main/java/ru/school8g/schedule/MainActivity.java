package ru.school8g.schedule;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.Window;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceError;

public class MainActivity extends Activity {
    private static final String HOST = "nikita2272282299.github.io";
    private static final String SITE = "https://" + HOST + "/school-schedule/?app=1";
    private static final String LOCAL = "file:///android_asset/site/index.html?app=1";
    static final String[] THEMES = {"aurora", "sunset", "ocean", "mint", "cosmos", "neon", "sakura", "ice", "newyear"};
    private WebView web;
    private boolean usedFallback = false;

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0A0814"));
        web.setLayerType(View.LAYER_TYPE_HARDWARE, null);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.setVerticalScrollBarEnabled(false);
        web.setHorizontalScrollBarEnabled(false);

        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setTextZoom(100);
        s.setUserAgentString(s.getUserAgentString() + " Raspisanie8GApp/2");

        web.addJavascriptInterface(new Bridge(), "AndroidApp");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                Uri u = Uri.parse(url);
                if (url.startsWith("file:///android_asset/site/") || ("https".equals(u.getScheme()) && HOST.equals(u.getHost()) && u.getPath().startsWith("/school-schedule/"))) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) { }
                return true;
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                view.evaluateJavascript("window.dispatchEvent(new Event('native-ready'));", null);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) onReceivedError(view, -1, "", request.getUrl().toString());
            }

            @Override
            public void onReceivedError(WebView view, int code, String desc, String failingUrl) {
                if (!usedFallback && failingUrl != null && failingUrl.equals(view.getUrl())) {
                    usedFallback = true;
                    view.loadUrl(LOCAL);
                }
            }
        });

        setContentView(web);
        if (state != null) web.restoreState(state);
        else web.loadUrl(SITE);

        final android.content.Context app = getApplicationContext();
        new Thread(new Runnable() {
            @Override
            public void run() {
                try {
                    Notif.channels(app);
                    Notif.scheduleJob(app);
                    Notif.scheduleNext(app);
                    Notif.check(app);
                } catch (Throwable ignored) { }
            }
        }).start();
        web.postDelayed(new Runnable() {
            @Override
            public void run() { askNotifPermission(false); }
        }, 2500);
    }

    private void askNotifPermission(boolean force) {
        if (force && !Notif.canPost(this) && (Build.VERSION.SDK_INT < 33 || checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED || (Notif.p(this).getBoolean("asked", false) && !shouldShowRequestPermissionRationale(Manifest.permission.POST_NOTIFICATIONS)))) {
            Intent settings = new Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS);
            settings.putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, getPackageName());
            if (Build.VERSION.SDK_INT < 26) {
                settings = new Intent(android.provider.Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getPackageName()));
            }
            try { startActivity(settings); } catch (Exception ignored) { }
            return;
        }
        if (Build.VERSION.SDK_INT < 33) return;
        if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) return;
        SharedPreferences p = Notif.p(this);
        if (!force && p.getBoolean("asked", false)) return;
        p.edit().putBoolean("asked", true).apply();
        try { requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 7); } catch (Throwable ignored) { }
    }

    /** Меняем иконку под тему, когда пользователь уходит из приложения (так ничего не дёргается). */
    private void applyIcon() {
        try {
            SharedPreferences p = Notif.p(this);
            String want = p.getString("icon", "aurora");
            boolean ok = false;
            for (String t : THEMES) if (t.equals(want)) ok = true;
            if (!ok) want = "aurora";
            String cur = p.getString("icon_applied", "aurora");
            if (want.equals(cur)) return;
            PackageManager pm = getPackageManager();
            String pkg = getPackageName();
            pm.setComponentEnabledSetting(new ComponentName(pkg, pkg + ".T_" + want),
                    PackageManager.COMPONENT_ENABLED_STATE_ENABLED, PackageManager.DONT_KILL_APP);
            for (String t : THEMES) {
                if (t.equals(want)) continue;
                pm.setComponentEnabledSetting(new ComponentName(pkg, pkg + ".T_" + t),
                        PackageManager.COMPONENT_ENABLED_STATE_DISABLED, PackageManager.DONT_KILL_APP);
            }
            p.edit().putString("icon_applied", want).apply();
        } catch (Throwable ignored) { }
    }

    private class Bridge {
        @JavascriptInterface
        public void setBars(final String color, final boolean light) {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    try {
                        int c = Color.parseColor(color.trim());
                        Window w = getWindow();
                        w.setStatusBarColor(c);
                        w.setNavigationBarColor(c);
                        web.setBackgroundColor(c);
                        if (Build.VERSION.SDK_INT >= 23) {
                            View d = w.getDecorView();
                            int f = d.getSystemUiVisibility();
                            f = light ? (f | View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR) : (f & ~View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
                            if (Build.VERSION.SDK_INT >= 26) {
                                f = light ? (f | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR) : (f & ~View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
                            }
                            d.setSystemUiVisibility(f);
                        }
                    } catch (Exception ignored) { }
                }
            });
        }

        @JavascriptInterface
        public void setIcon(String id) {
            if (id == null) return;
            Notif.p(MainActivity.this).edit().putString("icon", id.trim()).apply();
        }

        @JavascriptInterface
        public String getNotify() {
            SharedPreferences p = Notif.p(MainActivity.this);
            return "{\"n\":" + p.getBoolean("on_new", true) + ",\"l\":" + p.getBoolean("on_lessons", true)
                    + ",\"ok\":" + Notif.canPost(MainActivity.this) + ",\"exact\":" + Notif.exactAllowed(MainActivity.this) + "}";
        }

        @JavascriptInterface
        public void setNotify(boolean news, boolean lessons) {
            final android.content.Context c = getApplicationContext();
            Notif.p(c).edit().putBoolean("on_new", news).putBoolean("on_lessons", lessons).commit();
            if (news || lessons) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() { askNotifPermission(true); }
                });
            }
            new Thread(new Runnable() {
                @Override
                public void run() {
                    try {
                        Notif.scheduleJob(c);
                        Notif.scheduleNext(c);
                    } catch (Throwable ignored) { }
                }
            }).start();
        }

        @JavascriptInterface
        public boolean testNotify() {
            if (!Notif.canPost(MainActivity.this)) {
                runOnUiThread(new Runnable() {
                    @Override
                    public void run() { askNotifPermission(true); }
                });
                return false;
            }
            Notif.test(getApplicationContext());
            return true;
        }

        @JavascriptInterface
        public void openAlarmSettings() {
            runOnUiThread(() -> {
                if (Build.VERSION.SDK_INT >= 31 && !Notif.exactAllowed(MainActivity.this)) {
                    try { startActivity(new Intent(android.provider.Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM, Uri.parse("package:" + getPackageName()))); } catch (Exception ignored) { }
                }
            });
        }

        @JavascriptInterface
        public void setClass(String cls) {
            Notif.setClass(getApplicationContext(), cls);
        }

        @JavascriptInterface
        public void setDays(String json) {
            if (json == null || json.length() > 200000) return;
            final android.content.Context c = getApplicationContext();
            try {
                new org.json.JSONObject(json);
                Notif.p(c).edit().putString("days", json).commit();
                Notif.scheduleNext(c);
            } catch (Throwable ignored) { }
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onPause() { web.onPause(); super.onPause(); }

    @Override
    protected void onResume() {
        super.onResume();
        if (web != null) { web.onResume(); web.evaluateJavascript("window.dispatchEvent(new Event('native-ready'));", null); }
        final android.content.Context c = getApplicationContext();
        new Thread(() -> { try { Notif.scheduleJob(c); Notif.scheduleNext(c); } catch (Throwable ignored) { } }).start();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(requestCode, permissions, results);
        if (web != null) web.evaluateJavascript("window.dispatchEvent(new Event('native-ready'));", null);
        Notif.scheduleNext(getApplicationContext());
    }

    @Override
    protected void onStop() {
        super.onStop();
        applyIcon();
    }
}
