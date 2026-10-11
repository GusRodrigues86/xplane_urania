// =====================================================================================
// imgui_xplm.cpp - Dear ImGui in an X-Plane 12 window. See imgui_xplm.h.
//
// RENDERER: 2 versions. CMake selects one (URANIA_NATIVE_IMGUI).
//
// 1. Native (URANIA_NATIVE_IMGUI = 1, X-Plane SDK 4.4 with XPLMPanelGraphics.h):
//   The window has the content type "panel graphics". In its draw callback, X-Plane renders the
//   ImGui triangles itself (XPLMDrawCalls): ImDrawVert (x, y, u, v, RGBA8) and 16-bit indices have
//   the layout that XPLMDrawCalls expects. Panel graphics use global boxels (y up). The renderer
//   moves the origin to the window top-left corner and turns y down (transform stack), as the
//   SDK header shows. Then ImGui vertices and clip rectangles go in as they are.
//   Textures: XPLMCreateTexture (RGBA8). A texture update makes a new texture (the SDK has no
//   update call; the SDK says that a new texture in each frame is safe).
//
// 2. OpenGL (URANIA_NATIVE_IMGUI = 0, older SDK):
//   X-Plane calls the draw callback with OpenGL matrices for global boxels. The renderer
//   moves the ImGui coordinates (top-left origin) to the window corner, then draws the ImGui
//   triangles with OpenGL vertex arrays (OpenGL 1.1, like the ImGui opengl2 backend).
//   Textures: the renderer gets texture numbers from X-Plane (XPLMGenerateTextureNumbers) and
//   binds them with XPLMBindTexture2d, so the X-Plane texture state stays correct.
//   Clipping: the renderer projects the ImGui clip rectangles to pixels with the X-Plane view
//   matrices (datarefs sim/graphics/view/...), then uses glScissor.
//
// INPUT
//   Mouse: X-Plane click, wheel and cursor callbacks give global boxels. The code converts
//   them to window coordinates for ImGui.
//   Keyboard: X-Plane sends keys only to the window with keyboard focus. The window takes the
//   focus when ImGui wants text (example: you click into a number field) and gives it back after.
// =====================================================================================
#include "imgui_xplm.h"

#include <cfloat>
#include <cstdint>

#include <vector>

#include "imgui.h"
#include "XPLMDataAccess.h"
#include "XPLMDefs.h"
#include "XPLMGraphics.h"
#include "XPLMProcessing.h"

#if URANIA_NATIVE_IMGUI
#include "XPLMPanelGraphics.h"
#else
#if IBM
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <GL/gl.h>
#elif APL
#include <OpenGL/gl.h>
#else
#include <GL/gl.h>
#endif
#ifndef GL_CLAMP_TO_EDGE
#define GL_CLAMP_TO_EDGE 0x812F   // OpenGL 1.2. Windows gl.h has only OpenGL 1.1.
#endif
#endif

namespace {

// Selects one ImGui context for the time of a callback, then puts the old one back.
struct ContextScope {
    ImGuiContext* old;
    explicit ContextScope(ImGuiContext* c) : old(ImGui::GetCurrentContext()) { ImGui::SetCurrentContext(c); }
    ~ContextScope() { ImGui::SetCurrentContext(old); }
};

#if URANIA_NATIVE_IMGUI
// =====================================================================================
// Native renderer (XPLMPanelGraphics)
// =====================================================================================
static_assert(sizeof(ImDrawVert) == 5 * sizeof(float), "XPLMDrawCalls needs 5 floats per vertex (x, y, u, v, RGBA8)");
static_assert(sizeof(ImDrawIdx) == 2, "XPLMDrawCalls needs 16-bit indices");

void* tex_handle(ImTextureID id) { return reinterpret_cast<void*>(static_cast<intptr_t>(id)); }

void update_texture(ImTextureData* tex)
{
    if (tex->Status == ImTextureStatus_WantCreate || tex->Status == ImTextureStatus_WantUpdates) {
        if (tex->TexID != ImTextureID_Invalid)
            XPLMDestroyTexture(tex_handle(tex->TexID));
        void* h = XPLMCreateTexture(static_cast<const unsigned char*>(tex->GetPixels()), tex->Width, tex->Height);
        tex->SetTexID(static_cast<ImTextureID>(reinterpret_cast<intptr_t>(h)));
        tex->SetStatus(ImTextureStatus_OK);
    } else if (tex->Status == ImTextureStatus_WantDestroy) {
        if (tex->TexID != ImTextureID_Invalid)
            XPLMDestroyTexture(tex_handle(tex->TexID));
        tex->SetTexID(ImTextureID_Invalid);
        tex->SetStatus(ImTextureStatus_Destroyed);
    }
}

void render_lists(ImDrawData* dd, int left, int top)
{
    XPLMTransformPush();
    XPLMTransformTranslate(static_cast<float>(left), static_cast<float>(top));   // window top-left corner
    XPLMTransformScale(1.0f, -1.0f);                                             // y down, as ImGui
    XPLMTransformTranslate(-dd->DisplayPos.x, -dd->DisplayPos.y);
    std::vector<XPLMDrawCall_t> calls;
    for (const ImDrawList* list : dd->CmdLists) {
        XPLMMesh_t mesh;
        mesh.vertex_count = list->VtxBuffer.Size;
        mesh.vertices = reinterpret_cast<const float*>(list->VtxBuffer.Data);
        mesh.index_count = list->IdxBuffer.Size;
        mesh.indices = list->IdxBuffer.Data;
        calls.clear();
        for (const ImDrawCmd& cmd : list->CmdBuffer) {
            if (cmd.UserCallback) {
                if (cmd.UserCallback != ImGui::GetPlatformIO().DrawCallback_ResetRenderState)
                    cmd.UserCallback(list, &cmd);
                continue;
            }
            XPLMDrawCall_t c;
            c.tex_ref = tex_handle(cmd.GetTexID());
            c.scissors[0] = cmd.ClipRect.x;                      // 2 opposite corners, same space as the vertices
            c.scissors[1] = cmd.ClipRect.y;
            c.scissors[2] = cmd.ClipRect.z;
            c.scissors[3] = cmd.ClipRect.w;
            c.idx_offset = static_cast<int>(cmd.IdxOffset);
            c.element_count = static_cast<int>(cmd.ElemCount);
            c.vtx_offset = static_cast<int>(cmd.VtxOffset);
            calls.push_back(c);
        }
        if (!calls.empty())
            XPLMDrawCalls(&mesh, static_cast<int>(calls.size()), calls.data());
    }
    XPLMTransformPop();
}

#else
// X-Plane view matrices for the clip rectangles. Fallback: the OpenGL values.
XPLMDataRef g_mv_ref = nullptr, g_proj_ref = nullptr, g_vp_ref = nullptr;
bool g_refs_looked = false;

void view_matrices(float mv[16], float pj[16], int vp[4])
{
    if (!g_refs_looked) {
        g_mv_ref = XPLMFindDataRef("sim/graphics/view/modelview_matrix");
        g_proj_ref = XPLMFindDataRef("sim/graphics/view/projection_matrix");
        g_vp_ref = XPLMFindDataRef("sim/graphics/view/viewport");
        g_refs_looked = true;
    }
    if (g_mv_ref && g_proj_ref && g_vp_ref) {
        XPLMGetDatavf(g_mv_ref, mv, 0, 16);
        XPLMGetDatavf(g_proj_ref, pj, 0, 16);
        XPLMGetDatavi(g_vp_ref, vp, 0, 4);
    } else {
        glGetFloatv(GL_MODELVIEW_MATRIX, mv);
        glGetFloatv(GL_PROJECTION_MATRIX, pj);
        glGetIntegerv(GL_VIEWPORT, vp);
    }
}

// Global boxel point -> framebuffer pixel. Matrices are column-major (OpenGL order).
void to_pixel(const float mv[16], const float pj[16], const int vp[4], float x, float y, float& px, float& py)
{
    float e[4], c[4];
    for (int i = 0; i < 4; ++i)
        e[i] = mv[i] * x + mv[4 + i] * y + mv[12 + i];
    for (int i = 0; i < 4; ++i)
        c[i] = pj[i] * e[0] + pj[4 + i] * e[1] + pj[8 + i] * e[2] + pj[12 + i] * e[3];
    float w = (c[3] != 0.0f) ? c[3] : 1.0f;
    px = vp[0] + (c[0] / w + 1.0f) * 0.5f * vp[2];
    py = vp[1] + (c[1] / w + 1.0f) * 0.5f * vp[3];
}

void update_texture(ImTextureData* tex)
{
    if (tex->Status == ImTextureStatus_WantCreate) {
        int id = 0;
        XPLMGenerateTextureNumbers(&id, 1);
        XPLMBindTexture2d(id, 0);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, tex->Width, tex->Height, 0, GL_RGBA, GL_UNSIGNED_BYTE, tex->GetPixels());
        tex->SetTexID(static_cast<ImTextureID>(id));
        tex->SetStatus(ImTextureStatus_OK);
    } else if (tex->Status == ImTextureStatus_WantUpdates) {
        XPLMBindTexture2d(static_cast<int>(tex->TexID), 0);
        glPixelStorei(GL_UNPACK_ROW_LENGTH, tex->Width);
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
        for (ImTextureRect& r : tex->Updates)
            glTexSubImage2D(GL_TEXTURE_2D, 0, r.x, r.y, r.w, r.h, GL_RGBA, GL_UNSIGNED_BYTE, tex->GetPixelsAt(r.x, r.y));
        glPixelStorei(GL_UNPACK_ROW_LENGTH, 0);
        tex->SetStatus(ImTextureStatus_OK);
    } else if (tex->Status == ImTextureStatus_WantDestroy) {
        GLuint id = static_cast<GLuint>(tex->TexID);
        glDeleteTextures(1, &id);
        tex->SetTexID(ImTextureID_Invalid);
        tex->SetStatus(ImTextureStatus_Destroyed);
    }
}

#endif  // URANIA_NATIVE_IMGUI

ImGuiKey key_for(unsigned char vkey)
{
    switch (vkey) {
    case XPLM_VK_BACK: return ImGuiKey_Backspace;
    case XPLM_VK_TAB: return ImGuiKey_Tab;
    case XPLM_VK_RETURN: return ImGuiKey_Enter;
    case XPLM_VK_ENTER: return ImGuiKey_Enter;
    case XPLM_VK_NUMPAD_ENT: return ImGuiKey_KeypadEnter;
    case XPLM_VK_ESCAPE: return ImGuiKey_Escape;
    case XPLM_VK_END: return ImGuiKey_End;
    case XPLM_VK_HOME: return ImGuiKey_Home;
    case XPLM_VK_LEFT: return ImGuiKey_LeftArrow;
    case XPLM_VK_UP: return ImGuiKey_UpArrow;
    case XPLM_VK_RIGHT: return ImGuiKey_RightArrow;
    case XPLM_VK_DOWN: return ImGuiKey_DownArrow;
    case XPLM_VK_DELETE: return ImGuiKey_Delete;
    case XPLM_VK_A: return ImGuiKey_A;
    case XPLM_VK_C: return ImGuiKey_C;
    case XPLM_VK_V: return ImGuiKey_V;
    case XPLM_VK_X: return ImGuiKey_X;
    case XPLM_VK_Y: return ImGuiKey_Y;
    case XPLM_VK_Z: return ImGuiKey_Z;
    default: return ImGuiKey_None;
    }
}

}  // namespace

// =====================================================================================
// Window
// =====================================================================================
ImguiWindow::ImguiWindow(const char* title, int width, int height, std::function<void()> build)
    : build_(std::move(build))
{
    ImGuiContext* old = ImGui::GetCurrentContext();
    ctx_ = ImGui::CreateContext();
    ImGui::SetCurrentContext(ctx_);
    ImGuiIO& io = ImGui::GetIO();
    io.IniFilename = nullptr;                                   // no imgui.ini file
    io.LogFilename = nullptr;
    io.BackendPlatformName = "imgui_xplm";
    io.BackendRendererName = "imgui_xplm";
    io.BackendFlags |= ImGuiBackendFlags_RendererHasTextures;   // the renderer makes the font texture
    ImGui::StyleColorsDark();
    ImGuiStyle& style = ImGui::GetStyle();
    style.WindowRounding = 0.0f;
    style.WindowBorderSize = 0.0f;
    style.FontScaleMain = 1.15f;                                // text size (1.0 = 13 px)
    ImGui::SetCurrentContext(old);

    int sl = 0, st = 0, sr = 0, sb = 0;
    XPLMGetScreenBoundsGlobal(&sl, &st, &sr, &sb);
    XPLMCreateWindow_t p = {};
    p.structSize = sizeof(p);
    p.left = (sl + sr - width) / 2;
    p.right = p.left + width;
    p.top = (st + sb + height) / 2;
    p.bottom = p.top - height;
    p.visible = 0;
    p.drawWindowFunc = draw_cb;
    p.handleMouseClickFunc = left_click_cb;
    p.handleRightClickFunc = right_click_cb;
    p.handleKeyFunc = key_cb;
    p.handleCursorFunc = cursor_cb;
    p.handleMouseWheelFunc = wheel_cb;
    p.refcon = this;
    p.decorateAsFloatingWindow = xplm_WindowDecorationRoundRectangle;   // X-Plane frame: title, move, resize
    p.layer = xplm_WindowLayerFloatingWindows;
#if URANIA_NATIVE_IMGUI
    p.contentType = xplm_WindowContentTypePanelGraphics;          // X-Plane renders the ImGui draw data
#endif
    window_ = XPLMCreateWindowEx(&p);
    XPLMSetWindowPositioningMode(window_, xplm_WindowPositionFree, -1);
    XPLMSetWindowResizingLimits(window_, 320, 240, 1600, 1400);
    XPLMSetWindowTitle(window_, title);
}

ImguiWindow::~ImguiWindow()
{
    if (window_)
        XPLMDestroyWindow(window_);
    window_ = nullptr;
    ContextScope scope(ctx_);
    for (ImTextureData* tex : ImGui::GetPlatformIO().Textures)
        if (tex->TexID != ImTextureID_Invalid) {
            tex->SetStatus(ImTextureStatus_WantDestroy);
            update_texture(tex);
        }
    ImGui::DestroyContext(ctx_);
    ctx_ = nullptr;
}

void ImguiWindow::set_visible(bool visible)
{
    XPLMSetWindowIsVisible(window_, visible ? 1 : 0);
    if (visible)
        XPLMBringWindowToFront(window_);
    else if (XPLMHasKeyboardFocus(window_))
        XPLMTakeKeyboardFocus(nullptr);
}

bool ImguiWindow::visible() const { return window_ && XPLMGetWindowIsVisible(window_) != 0; }

// =====================================================================================
// Frame
// =====================================================================================
void ImguiWindow::draw()
{
    ContextScope scope(ctx_);
    ImGuiIO& io = ImGui::GetIO();
    int l = 0, t = 0, r = 0, b = 0;
    XPLMGetWindowGeometry(window_, &l, &t, &r, &b);
    left_ = l;
    top_ = t;
    io.DisplaySize = ImVec2(static_cast<float>(r - l), static_cast<float>(t - b));
    double now = XPLMGetElapsedTime();
    io.DeltaTime = (last_time_ > 0.0 && now > last_time_) ? static_cast<float>(now - last_time_) : 1.0f / 60.0f;
    last_time_ = now;

    // Hover: the mouse position comes from X-Plane each frame. Outside the window = no mouse.
    int mx = 0, my = 0;
    XPLMGetMouseLocationGlobal(&mx, &my);
    bool inside = mx >= l && mx < r && my <= t && my > b;
    if (inside || ImGui::IsAnyMouseDown())
        mouse_to_imgui(mx, my);
    else
        io.AddMousePosEvent(-FLT_MAX, -FLT_MAX);

    ImGui::NewFrame();
    ImGui::SetNextWindowPos(ImVec2(0.0f, 0.0f));
    ImGui::SetNextWindowSize(io.DisplaySize);
    ImGui::Begin("##imgui_xplm", nullptr,
                 ImGuiWindowFlags_NoTitleBar | ImGuiWindowFlags_NoResize | ImGuiWindowFlags_NoMove |
                     ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_NoSavedSettings |
                     ImGuiWindowFlags_NoBringToFrontOnFocus);
    if (build_)
        build_();
    ImGui::End();
    ImGui::Render();

    bool focus = XPLMHasKeyboardFocus(window_) != 0;
    if (io.WantTextInput && !focus)
        XPLMTakeKeyboardFocus(window_);
    else if (!io.WantTextInput && focus)
        XPLMTakeKeyboardFocus(nullptr);

    render(l, t);
}

void ImguiWindow::render(int left, int top)
{
    ImDrawData* dd = ImGui::GetDrawData();
    if (!dd)
        return;
    if (dd->Textures)
        for (ImTextureData* tex : *dd->Textures)
            if (tex->Status != ImTextureStatus_OK)
                update_texture(tex);
#if URANIA_NATIVE_IMGUI
    render_lists(dd, left, top);
#else
    float mv[16], pj[16];
    int vp[4];
    view_matrices(mv, pj, vp);

    // fog off, 1 texture unit, lighting off, alpha test off, alpha blend on, depth test off, depth write off
    XPLMSetGraphicsState(0, 1, 0, 0, 1, 0, 0);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    GLboolean old_scissor = glIsEnabled(GL_SCISSOR_TEST);
    GLint old_box[4];
    glGetIntegerv(GL_SCISSOR_BOX, old_box);
    glEnable(GL_SCISSOR_TEST);

    glMatrixMode(GL_MODELVIEW);
    glPushMatrix();
    glTranslatef(static_cast<float>(left), static_cast<float>(top), 0.0f);   // ImGui origin = window top-left
    glScalef(1.0f, -1.0f, 1.0f);                                             // ImGui y goes down
    glEnableClientState(GL_VERTEX_ARRAY);
    glEnableClientState(GL_TEXTURE_COORD_ARRAY);
    glEnableClientState(GL_COLOR_ARRAY);

    for (const ImDrawList* list : dd->CmdLists) {
        const ImDrawVert* vtx = list->VtxBuffer.Data;
        const ImDrawIdx* idx = list->IdxBuffer.Data;
        glVertexPointer(2, GL_FLOAT, sizeof(ImDrawVert), reinterpret_cast<const char*>(vtx) + offsetof(ImDrawVert, pos));
        glTexCoordPointer(2, GL_FLOAT, sizeof(ImDrawVert), reinterpret_cast<const char*>(vtx) + offsetof(ImDrawVert, uv));
        glColorPointer(4, GL_UNSIGNED_BYTE, sizeof(ImDrawVert), reinterpret_cast<const char*>(vtx) + offsetof(ImDrawVert, col));
        for (const ImDrawCmd& cmd : list->CmdBuffer) {
            if (cmd.UserCallback) {
                if (cmd.UserCallback != ImGui::GetPlatformIO().DrawCallback_ResetRenderState)
                    cmd.UserCallback(list, &cmd);
                continue;
            }
            // Clip rectangle: ImGui coordinates -> global boxels -> pixels.
            float x0, y0, x1, y1;
            to_pixel(mv, pj, vp, left + cmd.ClipRect.x, top - cmd.ClipRect.w, x0, y0);
            to_pixel(mv, pj, vp, left + cmd.ClipRect.z, top - cmd.ClipRect.y, x1, y1);
            if (x1 <= x0 || y1 <= y0)
                continue;
            glScissor(static_cast<GLint>(x0), static_cast<GLint>(y0), static_cast<GLsizei>(x1 - x0 + 0.5f),
                      static_cast<GLsizei>(y1 - y0 + 0.5f));
            XPLMBindTexture2d(static_cast<int>(cmd.GetTexID()), 0);
            glDrawElements(GL_TRIANGLES, static_cast<GLsizei>(cmd.ElemCount),
                           sizeof(ImDrawIdx) == 2 ? GL_UNSIGNED_SHORT : GL_UNSIGNED_INT, idx + cmd.IdxOffset);
        }
    }

    glDisableClientState(GL_COLOR_ARRAY);
    glDisableClientState(GL_TEXTURE_COORD_ARRAY);
    glDisableClientState(GL_VERTEX_ARRAY);
    glPopMatrix();
    glScissor(old_box[0], old_box[1], old_box[2], old_box[3]);
    if (!old_scissor)
        glDisable(GL_SCISSOR_TEST);
#endif
}

// =====================================================================================
// Input
// =====================================================================================
void ImguiWindow::mouse_to_imgui(int x, int y)
{
    ImGui::GetIO().AddMousePosEvent(static_cast<float>(x - left_), static_cast<float>(top_ - y));
}

int ImguiWindow::click(int x, int y, XPLMMouseStatus status, int button)
{
    ContextScope scope(ctx_);
    int r = 0, b = 0;
    XPLMGetWindowGeometry(window_, &left_, &top_, &r, &b);
    mouse_to_imgui(x, y);
    ImGuiIO& io = ImGui::GetIO();
    if (status == xplm_MouseDown)
        io.AddMouseButtonEvent(button, true);
    else if (status == xplm_MouseUp)
        io.AddMouseButtonEvent(button, false);
    return 1;                                                  // the window uses the click
}

void ImguiWindow::draw_cb(XPLMWindowID, void* refcon) { static_cast<ImguiWindow*>(refcon)->draw(); }

int ImguiWindow::left_click_cb(XPLMWindowID, int x, int y, XPLMMouseStatus status, void* refcon)
{
    return static_cast<ImguiWindow*>(refcon)->click(x, y, status, 0);
}

int ImguiWindow::right_click_cb(XPLMWindowID, int x, int y, XPLMMouseStatus status, void* refcon)
{
    return static_cast<ImguiWindow*>(refcon)->click(x, y, status, 1);
}

XPLMCursorStatus ImguiWindow::cursor_cb(XPLMWindowID, int x, int y, void* refcon)
{
    ImguiWindow* w = static_cast<ImguiWindow*>(refcon);
    ContextScope scope(w->ctx_);
    w->mouse_to_imgui(x, y);
    return xplm_CursorDefault;
}

int ImguiWindow::wheel_cb(XPLMWindowID, int x, int y, int wheel, int clicks, void* refcon)
{
    ImguiWindow* w = static_cast<ImguiWindow*>(refcon);
    ContextScope scope(w->ctx_);
    w->mouse_to_imgui(x, y);
    // wheel 0 = vertical, 1 = horizontal
    ImGui::GetIO().AddMouseWheelEvent(wheel == 1 ? static_cast<float>(clicks) : 0.0f,
                                      wheel == 0 ? static_cast<float>(clicks) : 0.0f);
    return 1;
}

void ImguiWindow::key_cb(XPLMWindowID, char key, XPLMKeyFlags flags, char vkey, void* refcon, int losing_focus)
{
    ImguiWindow* w = static_cast<ImguiWindow*>(refcon);
    ContextScope scope(w->ctx_);
    ImGuiIO& io = ImGui::GetIO();
    if (losing_focus) {
        io.AddFocusEvent(false);                                // releases all keys
        return;
    }
    io.AddKeyEvent(ImGuiMod_Ctrl, (flags & xplm_ControlFlag) != 0);
    io.AddKeyEvent(ImGuiMod_Shift, (flags & xplm_ShiftFlag) != 0);
    io.AddKeyEvent(ImGuiMod_Alt, (flags & xplm_OptionAltFlag) != 0);
    ImGuiKey k = key_for(static_cast<unsigned char>(vkey));
    if (k != ImGuiKey_None) {
        if (flags & xplm_DownFlag)
            io.AddKeyEvent(k, true);
        if (flags & xplm_UpFlag)
            io.AddKeyEvent(k, false);
    }
    unsigned char c = static_cast<unsigned char>(key);
    if ((flags & xplm_DownFlag) && !(flags & xplm_ControlFlag) && c >= 32 && c != 127)
        io.AddInputCharacter(c);
}
