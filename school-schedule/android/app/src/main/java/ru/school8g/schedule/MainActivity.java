package ru.school8g.schedule;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
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

public class MainActivity extends Activity {
    private static final String HOST = "nikita2272282299.github.io";
    private static final String SITE = "https://" + HOST + "/school-schedule/?app=1";
    private static final String LOCAL = "file:///android_asset/site/index.html?app=1";
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
        s.setUserAgentString(s.getUserAgentString() + " Raspisanie8GApp/1");

        web.addJavascriptInterface(new Bridge(), "AndroidApp");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                Uri u = Uri.parse(url);
                if (url.startsWith("file:") || HOST.equals(u.getHost())) return false;
                try { startActivity(new Intent(Intent.ACTION_VIEW, u)); } catch (Exception ignored) { }
                return true;
            }

            @Override
            public void onReceivedError(WebView view, int code, String desc, String failingUrl) {
                if (!usedFallback && failingUrl != null && failingUrl.startsWith("http")) {
                    usedFallback = true;
                    view.loadUrl(LOCAL);
                }
            }
        });

        setContentView(web);
        if (state != null) web.restoreState(state);
        else web.loadUrl(SITE);
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
    protected void onResume() { super.onResume(); web.onResume(); }
}
