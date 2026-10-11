// =====================================================================================
// imgui_xplm.h - Dear ImGui in an X-Plane 12 window (XPLM modern window + OpenGL renderer).
//
// One ImguiWindow = one X-Plane floating window with one ImGui context.
// X-Plane gives the window frame (title bar, move, resize). ImGui fills the inside.
//
// Usage:
//   ImguiWindow win("Urania", 460, 520, [] { ImGui::Text("Hello"); });
//   win.set_visible(true);
// The function that you give is called in each frame while the window is visible.
// Put ImGui widget calls in it (ImGui::Text, ImGui::SliderFloat, ImGui::Button ...).
//
// GLOSSARY
//   boxel   X-Plane user-interface unit. 1 boxel = 1 pixel at 100 % UI size.
//   global  X-Plane desktop coordinates: origin bottom-left, y goes up.
//   ImGui   coordinates inside the window: origin top-left, y goes down.
// =====================================================================================
#pragma once

#include <functional>
#include <string>

#include "XPLMDisplay.h"

struct ImGuiContext;

class ImguiWindow {
public:
    ImguiWindow(const char* title, int width, int height, std::function<void()> build);
    ~ImguiWindow();
    ImguiWindow(const ImguiWindow&) = delete;
    ImguiWindow& operator=(const ImguiWindow&) = delete;

    void set_visible(bool visible);
    bool visible() const;

private:
    // X-Plane callbacks (refcon = this).
    static void draw_cb(XPLMWindowID id, void* refcon);
    static int left_click_cb(XPLMWindowID id, int x, int y, XPLMMouseStatus status, void* refcon);
    static int right_click_cb(XPLMWindowID id, int x, int y, XPLMMouseStatus status, void* refcon);
    static void key_cb(XPLMWindowID id, char key, XPLMKeyFlags flags, char vkey, void* refcon, int losing_focus);
    static XPLMCursorStatus cursor_cb(XPLMWindowID id, int x, int y, void* refcon);
    static int wheel_cb(XPLMWindowID id, int x, int y, int wheel, int clicks, void* refcon);

    void draw();
    int click(int x, int y, XPLMMouseStatus status, int button);
    void mouse_to_imgui(int x, int y);
    void render(int left, int top);

    XPLMWindowID window_ = nullptr;
    ImGuiContext* ctx_ = nullptr;
    std::function<void()> build_;
    double last_time_ = 0.0;
    int left_ = 0, top_ = 0;          // window top-left corner, global boxels (last frame)
};
