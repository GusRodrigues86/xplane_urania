// =====================================================================================
// urania.cpp - Urania plugin for X-Plane 12. Companion of the Urania night sky files.
//
// The night sky shader (astronomical.xsa) paints the stars, the Milky Way, nebulae, galaxies
// and the moonlit sky. A shader cannot change datarefs, and X-Plane gives the shader no plugin
// input. This plugin has a settings window (Dear ImGui). Release v1 has parts 0, 1 and 2.
// Parts 3 and 4 are test parts (CMake option URANIA_DEV=ON):
//
//   0. Sky files         Checks that the Urania shader and star file are installed (sky_files.cpp).
//                        An X-Plane update can replace them: the window then says "run Urania again".
//                        Menu "Restore X-Plane stock sky..." copies the user's original files back.
//   1. Cloud moonlight   sim/private/controls/lighting/E_moon_lx (X-Plane default 0.6, tested 2.4).
//                        Steps 0.6, 1.2, 2.4, 4.8. Saved. Written at the start of each flight and after each load.
//   2. Sky darkness      sim/private/controls/stars/gain_photometric (X-Plane default 20). Live.
//                        X-Plane uses it for stars and haze (Milky Way, nebulae, galaxies). Gus pick
//                        2026-10-10: the haze follows it (shader HAZE_EMISSIVE = 0).
//                        Level 1..9 = Bortle 9..1, 0.5 magnitude per level. Saved.
//   3. Sky gains         star, Milky Way, nebula and galaxy gains in astronomical.xsa
//                        (xsa_gains.cpp). Shown after an X-Plane restart.
//   4. Haze test         private scattering and fog datarefs, for tests. Not saved.
//
// The plugin keeps the X-Plane value of each dataref before it changes it. When you turn the
// plugin off (menu or Plugin Admin), it puts the X-Plane values back.
//
// To add a dataref slider: add a row to g_tests (section 2). Only this file changes.
//
// Menu Plugins > Urania: Settings window, Cloud moonlight on, Log values, Restore X-Plane stock sky...
// Commands (Settings > Keyboard): urania/window, urania/toggle, urania/brighter, urania/dimmer.
// The plugin saves the settings in Output/preferences/Urania.prf (first start: it reads NightSky.prf).
//
// GLOSSARY
//   dataref      A named value inside X-Plane. Plugins read and write it by name.
//   private      A dataref under sim/private/. Laminar Research can change or remove it
//                in an X-Plane update. If the dataref is not found, the plugin does nothing.
// =====================================================================================
#include <algorithm>
#include <cmath>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "imgui.h"
#include "imgui_xplm.h"
#include "sky_files.h"
#include "xsa_gains.h"

#include "XPLMDataAccess.h"
#include "XPLMMenus.h"
#include "XPLMPlugin.h"
#include "XPLMProcessing.h"
#include "XPLMUtilities.h"

// URANIA_DEV = 1 (CMake option): add the test parts (sky gains in the shader file, moon info,
// haze test sliders). URANIA_DEV = 0 (release v1): cloud moonlight and star light only.
#ifndef URANIA_DEV
#define URANIA_DEV 0
#endif

namespace {

void log_line(const char* fmt, ...)
{
    char text[512];
    int n = std::snprintf(text, sizeof(text), "Urania %s: ", URANIA_VERSION);
    va_list args;
    va_start(args, fmt);
    std::vsnprintf(text + n, sizeof(text) - n - 1, fmt, args);
    va_end(args);
    std::strncat(text, "\n", sizeof(text) - std::strlen(text) - 1);
    XPLMDebugString(text);
}

// =====================================================================================
// 1. DATAREF ACCESS
// =====================================================================================
// Fallback for XPLMFindDataRef: the full dataref list (XPLM400), as DataRefTool reads it.
// Gus test 2026-10-10: XPLMFindDataRef gives nothing for sim/private datarefs, but DataRefTool
// shows them. The list keeps only names under sim/private/. It reads only new list entries.
XPLMDataRef find_in_list(const char* name)
{
    static std::map<std::string, XPLMDataRef> s_private;
    static int s_count = 0;
    static bool s_logged = false;
    int n = XPLMCountDataRefs();
    if (n > s_count) {
        std::vector<XPLMDataRef> refs(static_cast<size_t>(n - s_count));
        XPLMGetDataRefsByIndex(s_count, n - s_count, refs.data());
        for (XPLMDataRef r : refs) {
            XPLMDataRefInfo_t info = {};
            info.structSize = sizeof(info);
            XPLMGetDataRefInfo(r, &info);
            if (info.name && std::strncmp(info.name, "sim/private/", 12) == 0)
                s_private[info.name] = r;
        }
        s_count = n;
        if (!s_logged) {
            log_line("dataref list: %d datarefs, %d under sim/private/", n, static_cast<int>(s_private.size()));
            s_logged = true;
        }
    }
    auto it = s_private.find(name);
    return (it != s_private.end()) ? it->second : nullptr;
}

XPLMDataRef find_ref(const char* name)
{
    XPLMDataRef r = XPLMFindDataRef(name);
    return r ? r : find_in_list(name);
}

// A dataref that the plugin can change. The plugin keeps the X-Plane value before the first change.
struct Ref {
    const char* name;
    XPLMDataRef ref = nullptr;
    int type = 0;               // XPLMDataTypeID bits
    double original = 0.0;      // X-Plane value before the first change
    bool have_original = false;
    bool changed = false;       // the plugin wrote a value

    explicit Ref(const char* n) : name(n) {}

    bool bad_type = false;      // the dataref exists, but it is not a number

    // first = true: at plugin enable (log a missing dataref). first = false: a later retry (log only success).
    bool find(bool first = true)
    {
        if (bad_type)
            return false;
        ref = find_ref(name);
        type = ref ? static_cast<int>(XPLMGetDataRefTypes(ref)) : 0;
        if (ref && !(type & (xplmType_Float | xplmType_Double | xplmType_Int))) {
            log_line("dataref %s has type %d. The plugin does not use it.", name, type);
            ref = nullptr;
            bad_type = true;
        }
        if (!ref && first)
            log_line("dataref not found yet: %s (the plugin tries again every 2 s)", name);
        if (ref && !first)
            log_line("dataref found: %s", name);
        have_original = false;
        changed = false;
        return ref != nullptr;
    }
    double get() const
    {
        if (!ref)
            return 0.0;
        if (type & xplmType_Float)
            return XPLMGetDataf(ref);
        if (type & xplmType_Double)
            return XPLMGetDatad(ref);
        return XPLMGetDatai(ref);
    }
    void keep_original()
    {
        if (ref && !have_original) {
            original = get();
            have_original = true;
        }
    }
    void set(double v)
    {
        if (!ref)
            return;
        keep_original();
        if (type & xplmType_Float)
            XPLMSetDataf(ref, static_cast<float>(v));
        else if (type & xplmType_Double)
            XPLMSetDatad(ref, v);
        else
            XPLMSetDatai(ref, static_cast<int>(std::lround(v)));
        changed = true;
    }
    void restore()
    {
        if (ref && have_original && changed) {
            set(original);
            changed = false;
            log_line("X-Plane value back: %s = %.4g", name, original);
        }
    }
};

// Read-only value for the window.
struct Info {
    const char* name;
    XPLMDataRef ref = nullptr;
    explicit Info(const char* n) : name(n) {}
    void find() { ref = find_ref(name); }
    float get() const { return ref ? XPLMGetDataf(ref) : NAN; }
};

// =====================================================================================
// 2. SETTINGS AND DATAREFS
// =====================================================================================
const float kCloudDefault = 2.4f;                              // E_moon_lx, tested (Gus, 2026-10-10)
// E_moon_lx steps (Gus, 2026-10-11). 0.6 = X-Plane default. Each step = x2.
const float kCloudSteps[] = {0.6f, 1.2f, 2.4f, 4.8f};
const int kCloudStepCount = 4;

int cloud_step(float v)                                        // nearest step index
{
    int best = 0;
    for (int i = 1; i < kCloudStepCount; ++i)
        if (std::fabs(kCloudSteps[i] - v) < std::fabs(kCloudSteps[best] - v))
            best = i;
    return best;
}
const float kMoonNits = 785.0f;                                // moon shader calibration value

bool g_on = true;                                              // cloud moonlight on
float g_cloud = kCloudDefault;
// Sky darkness level 1..9 (1 = Bortle 9 city sky, 9 = Bortle 1 dark site). Each level = 0.5 magnitude.
// Level kDarkAnchor = the X-Plane value of gain_photometric (default 20).
const int kDarkMin = 1, kDarkMax = 9, kDarkAnchor = 5;
const float kMagPerLevel = 0.5f;
int g_dark = kDarkAnchor;

double dark_factor(int level) { return std::pow(10.0, 0.4 * kMagPerLevel * (level - kDarkAnchor)); }

Ref g_cloud_ref("sim/private/controls/lighting/E_moon_lx");
Ref g_star_ref("sim/private/controls/stars/gain_photometric");

Info g_nits("sim/private/controls/moon/nits");
Info g_moon_pitch("sim/graphics/scenery/moon_pitch_degrees");
Info g_moon_illum("sim/graphics/scenery/moon_illumination");
Info g_sun_pitch("sim/graphics/scenery/sun_pitch_degrees");
Info g_mon_amb("sim/private/stats/skyc/mon_amb_g");
Info g_sun_amb("sim/private/stats/skyc/sun_amb_g");

// Test sliders (section 4 of the window). Not saved. To add a slider, add a row.
struct TestRow {
    const char* label;
    Ref ref;
    float min, max;
    bool log_scale;
    const char* format;
    float value = 0.0f;
};
TestRow g_tests[] = {
    {"Visibility override (m, 0 = off)", Ref("sim/private/controls/scattering/override_visibility_m"), 0.0f, 200000.0f, false, "%.0f"},
    {"Turbidity", Ref("sim/private/controls/scattering/override_turbidity_t"), 0.5f, 10.0f, false, "%.3f"},
    {"Fog mix", Ref("sim/private/controls/scattering/fog_mix"), 0.0f, 1.0f, false, "%.2f"},
    {"Volumetric fog min light", Ref("sim/private/controls/volumetric/fog/min_light"), 0.0f, 2.0f, false, "%.2f"},
    {"Fog albedo", Ref("sim/private/controls/atmo/fog_albedo"), 0.0f, 1.0f, false, "%.2f"},
};

// Sky files (part 0).
SkyPaths g_sky;
SkyCheck g_sky_check;
bool g_confirm_restore = false;   // the window shows the restore question
std::string g_restore_msg;        // result of the last restore

// Sky gains in astronomical.xsa.
std::string g_xsa_path;
SkyGains g_file_gains;        // values in the file now
SkyGains g_edit_gains;        // values in the window
bool g_gains_ok = false;
std::string g_gains_msg;
#if URANIA_DEV
bool g_gains_written = false;  // written in this session: restart X-Plane
#endif

// =====================================================================================
// 3. APPLY AND RESTORE
// =====================================================================================
void apply(const char* why)
{
    if (g_cloud_ref.ref) {
        g_cloud_ref.keep_original();
        g_cloud_ref.set(g_on ? g_cloud : g_cloud_ref.original);
        log_line("%s: E_moon_lx %.2f (read back %.2f, X-Plane value %.2f)", why, g_on ? g_cloud : g_cloud_ref.original,
                 g_cloud_ref.get(), g_cloud_ref.original);
    }
    if (g_star_ref.ref) {
        g_star_ref.keep_original();
        if (g_dark != kDarkAnchor || g_star_ref.changed)
            g_star_ref.set(g_star_ref.original * dark_factor(g_dark));
    }
}

void restore_all()
{
    g_cloud_ref.restore();
    g_star_ref.restore();
#if URANIA_DEV
    for (TestRow& t : g_tests)
        t.ref.restore();
#endif
}

void check_nits()
{
    float nits = g_nits.get();
    if (!std::isnan(nits) && std::fabs(nits - kMoonNits) > 0.5f)
        log_line("NOTE: moon/nits is %.0f. The moon shader is calibrated for %.0f.", nits, kMoonNits);
}

#if URANIA_DEV
void load_gains()
{
    std::string err;
    g_gains_ok = read_sky_gains(g_xsa_path, g_file_gains, err);
    if (g_gains_ok) {
        g_edit_gains = g_file_gains;
        g_gains_msg.clear();
    } else {
        g_gains_msg = err;
        log_line("sky gains: %s", err.c_str());
    }
}
#endif

// =====================================================================================
// 4. SAVED SETTINGS (Output/preferences/Urania.prf)
// =====================================================================================
std::string prefs_file(const char* name = "Urania.prf")
{
    char path[1024] = {};
    XPLMGetPrefsPath(path);                                              // .../Output/preferences/Set X-Plane.prf
    std::string p(path);
    size_t cut = p.find_last_of("/\\");
    return (cut == std::string::npos ? std::string() : p.substr(0, cut + 1)) + name;
}

float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

void load_prefs()
{
    std::string file = prefs_file();
    FILE* f = std::fopen(file.c_str(), "r");
    if (!f) {
        // First start of Urania: take the settings of the NightSky plugin (the earlier name), if any.
        std::string old = prefs_file("NightSky.prf");
        f = std::fopen(old.c_str(), "r");
        if (f)
            log_line("no %s yet: settings from %s", file.c_str(), old.c_str());
    }
    if (!f) {
        log_line("no settings file yet (%s). Default settings.", file.c_str());
        return;
    }
    char key[64];
    float value;
    while (std::fscanf(f, "%63s %f", key, &value) == 2) {
        if (std::strcmp(key, "on") == 0)
            g_on = value != 0.0f;
        else if (std::strcmp(key, "cloud_moon_lx") == 0)
            g_cloud = kCloudSteps[cloud_step(value)];
        else if (std::strcmp(key, "sky_darkness") == 0)
            g_dark = static_cast<int>(clampf(value, kDarkMin, kDarkMax));
    }
    std::fclose(f);
    log_line("settings loaded: on %d, cloud moonlight %.2f, sky darkness %d", g_on, g_cloud, g_dark);
}

void save_prefs()
{
    std::string file = prefs_file();
    FILE* f = std::fopen(file.c_str(), "w");
    if (!f) {
        log_line("ERROR: cannot write %s", file.c_str());
        return;
    }
    std::fprintf(f, "on %d\ncloud_moon_lx %.3f\nsky_darkness %d\n", g_on ? 1 : 0, g_cloud, g_dark);
    std::fclose(f);
}

void log_values()
{
    log_line("now: E_moon_lx %.2f (X-Plane %.2f), gain_photometric %.4g (X-Plane %.4g), moon/nits %.0f",
             g_cloud_ref.get(), g_cloud_ref.original, g_star_ref.get(), g_star_ref.original, g_nits.get());
#if URANIA_DEV
    for (TestRow& t : g_tests)
        if (t.ref.ref)
            log_line("now: %s = %.4g (X-Plane %.4g)", t.ref.name, t.ref.get(), t.ref.have_original ? t.ref.original : t.ref.get());
#endif
    if (g_gains_ok)
        log_line("file gains: star %.3f, Milky Way %.3f, nebula %.3f, galaxy %.3f", g_file_gains.value[0],
                 g_file_gains.value[1], g_file_gains.value[2], g_file_gains.value[3]);
}

// =====================================================================================
// 5. SETTINGS WINDOW (Dear ImGui)
// =====================================================================================
std::unique_ptr<ImguiWindow> g_window;
XPLMMenuID g_menu = nullptr;
int g_idx_window = -1, g_idx_on = -1;

void update_menu();

void help(const char* text)
{
    ImGui::SameLine();
    ImGui::TextDisabled("(?)");
    if (ImGui::BeginItemTooltip()) {
        ImGui::PushTextWrapPos(ImGui::GetFontSize() * 28.0f);
        ImGui::TextUnformatted(text);
        ImGui::PopTextWrapPos();
        ImGui::EndTooltip();
    }
}

// --- Part 0: sky files -------------------------------------------------------------
bool g_open_sky = false;          // open the "Sky files" header in the next frame

void check_sky()
{
    g_sky_check = check_sky_files(g_sky);
    log_line("sky files: %s", g_sky_check.detail.c_str());
}

void do_restore()
{
    std::string err;
    if (restore_stock_sky(g_sky, err)) {
        g_restore_msg = "Done. Restart X-Plane to see the X-Plane stock sky.";
        log_line("restore: the X-Plane stock sky files are back (%s, %s)", g_sky.xsa.c_str(), g_sky.dat.c_str());
    } else {
        g_restore_msg = "Restore failed: " + err;
        log_line("ERROR: restore: %s", err.c_str());
    }
    g_confirm_restore = false;
    check_sky();
}

void ui_sky()
{
    const ImVec4 warn(1, 0.75f, 0.35f, 1);
    if (g_sky_check.state == SkyState::kReplaced) {
        ImGui::PushTextWrapPos(0.0f);
        ImGui::TextColored(warn, "X-Plane update? The Urania sky files were %s", g_sky_check.detail.c_str());
        ImGui::PopTextWrapPos();
    }
    if (g_open_sky) {
        ImGui::SetNextItemOpen(true);
        g_open_sky = false;
    }
    if (!ImGui::CollapsingHeader("Sky files"))
        return;
    if (g_sky_check.state == SkyState::kInstalled)
        ImGui::TextDisabled("%s", g_sky_check.detail.c_str());
    else if (g_sky_check.state == SkyState::kNoManifest)
        ImGui::TextDisabled("Not installed from a Urania zip (%s).", g_sky_check.detail.c_str());
    bool have_backup = file_size(g_sky.backup_xsa) > 0 && file_size(g_sky.backup_dat) > 0;
    if (!g_confirm_restore) {
        ImGui::BeginDisabled(!have_backup);
        if (ImGui::Button("Restore X-Plane stock sky..."))
            g_confirm_restore = true;
        ImGui::EndDisabled();
        help("Copies your original X-Plane files (Resources/plugins/Urania/backup) back:\n"
             "astronomical.xsa and earth_astro.dat. X-Plane shows the stock sky after a restart.\n"
             "To install Urania again, extract the Urania zip again.");
    } else {
        ImGui::PushTextWrapPos(0.0f);
        ImGui::TextColored(warn, "Put the X-Plane stock sky files back? Urania stars and Milky Way go away "
                                 "after the next X-Plane start.");
        ImGui::PopTextWrapPos();
        if (ImGui::Button("Restore now"))
            do_restore();
        ImGui::SameLine();
        if (ImGui::Button("Cancel"))
            g_confirm_restore = false;
    }
    if (!g_restore_msg.empty())
        ImGui::TextWrapped("%s", g_restore_msg.c_str());
}

void ui_cloud()
{
    if (!ImGui::CollapsingHeader("Cloud moonlight", ImGuiTreeNodeFlags_DefaultOpen))
        return;
    if (!g_cloud_ref.ref) {
        ImGui::TextColored(ImVec4(1, 0.5f, 0.3f, 1), "Dataref E_moon_lx not found.");
        return;
    }
    if (ImGui::Checkbox("On", &g_on)) {
        apply("window");
        save_prefs();
        update_menu();
    }
    help("Moonlight on the clouds. Steps 0.6, 1.2, 2.4, 4.8 (0.6 = X-Plane default, 2.4 = tested).\n"
         "On: Urania value. Off: X-Plane value.\nDataref sim/private/controls/lighting/E_moon_lx.");
    ImGui::BeginDisabled(!g_on);
    int step = cloud_step(g_cloud);
    char label[32];
    std::snprintf(label, sizeof(label), "%.1f", kCloudSteps[step]);
    ImGui::SetNextItemWidth(-90.0f);
    if (ImGui::SliderInt("##cloud", &step, 0, kCloudStepCount - 1, label, ImGuiSliderFlags_AlwaysClamp)) {
        g_cloud = kCloudSteps[step];
        apply("window");
    }
    if (ImGui::IsItemDeactivatedAfterEdit())
        save_prefs();
    ImGui::SameLine();
    if (ImGui::Button("2.4##cloud")) {
        g_cloud = kCloudDefault;
        apply("window");
        save_prefs();
    }
    ImGui::EndDisabled();
    ImGui::TextDisabled("Now %.2f   X-Plane value %.2f   tested 2.4", g_cloud_ref.get(), g_cloud_ref.original);
}

void ui_star_light()
{
    if (!ImGui::CollapsingHeader("Sky darkness: star light (live)", ImGuiTreeNodeFlags_DefaultOpen))
        return;
    if (!g_star_ref.ref) {
        ImGui::TextColored(ImVec4(1, 0.5f, 0.3f, 1), "Dataref gain_photometric not found.");
        return;
    }
    ImGui::SetNextItemWidth(-90.0f);
    char label[32];
    std::snprintf(label, sizeof(label), "%d = Bortle %d", g_dark, 10 - g_dark);
    if (ImGui::SliderInt("##dark", &g_dark, kDarkMin, kDarkMax, label, ImGuiSliderFlags_AlwaysClamp))
        apply("window");
    if (ImGui::IsItemDeactivatedAfterEdit())
        save_prefs();
    ImGui::SameLine();
    if (ImGui::Button("5##dark")) {
        g_dark = kDarkAnchor;
        apply("window");
        save_prefs();
    }
    help("1 = Bortle 9 (city sky), 9 = Bortle 1 (dark site). Stars, Milky Way, nebulae and galaxies.\n"
         "Each level = 0.5 magnitude (x1.58). Level 5 = X-Plane value.\n"
         "Dataref sim/private/controls/stars/gain_photometric. The change is live.");
    ImGui::TextDisabled("Now %.4g   X-Plane value %.4g", g_star_ref.get(), g_star_ref.original);
    if (g_gains_ok && g_file_gains.haze_emissive > 0.0f)
        ImGui::TextDisabled("This shader build: the Milky Way stays at star light %.4g.", g_file_gains.haze_emissive);
}

#if URANIA_DEV
void ui_gains()
{
    if (!ImGui::CollapsingHeader("Sky gains (X-Plane restart)", ImGuiTreeNodeFlags_DefaultOpen))
        return;
    if (!g_gains_ok) {
        ImGui::PushTextWrapPos(0.0f);
        ImGui::TextColored(ImVec4(1, 0.5f, 0.3f, 1), "%s", g_gains_msg.c_str());
        ImGui::PopTextWrapPos();
        if (ImGui::Button("Read again"))
            load_gains();
        return;
    }
    static const char* const labels[kGainCount] = {"Stars", "Milky Way", "Nebulae", "Galaxies"};
    static const float lo[kGainCount] = {0.02f, 0.1f, 0.5f, 0.5f};
    static const float hi[kGainCount] = {3.0f, 30.0f, 400.0f, 400.0f};
    for (int g = 0; g < kGainCount; ++g) {
        ImGui::PushID(g);
        ImGui::SetNextItemWidth(-140.0f);
        ImGui::SliderFloat("##gain", &g_edit_gains.value[g], lo[g], hi[g], "%.3g", ImGuiSliderFlags_Logarithmic);
        ImGui::SameLine();
        bool diff = std::fabs(g_edit_gains.value[g] - g_file_gains.value[g]) > 1e-6f;
        if (diff)
            ImGui::TextColored(ImVec4(1, 0.85f, 0.3f, 1), "%s *", labels[g]);
        else
            ImGui::TextUnformatted(labels[g]);
        ImGui::PopID();
    }
    bool pending = false;
    for (int g = 0; g < kGainCount; ++g)
        pending |= std::fabs(g_edit_gains.value[g] - g_file_gains.value[g]) > 1e-6f;
    ImGui::BeginDisabled(!pending);
    if (ImGui::Button("Write to shader file")) {
        std::string err;
        if (write_sky_gains(g_xsa_path, g_edit_gains, err)) {
            g_gains_written = true;
            log_line("sky gains written: star %.3f, Milky Way %.3f, nebula %.3f, galaxy %.3f", g_edit_gains.value[0],
                     g_edit_gains.value[1], g_edit_gains.value[2], g_edit_gains.value[3]);
            load_gains();
        } else {
            g_gains_msg = err;
            log_line("ERROR: sky gains not written: %s", err.c_str());
        }
    }
    ImGui::SameLine();
    if (ImGui::Button("Undo"))
        g_edit_gains = g_file_gains;
    ImGui::EndDisabled();
    ImGui::SameLine();
    if (ImGui::Button("Tested values"))
        for (int g = 0; g < kGainCount; ++g)
            g_edit_gains.value[g] = kGainDefault[g];
    help("Gains inside astronomical.xsa. X-Plane reads the shader file when it starts.\n"
         "Write the values, then restart X-Plane. Tested: stars 0.35, Milky Way 3, nebulae 40, galaxies 40.\n"
         "Before the first change, the plugin keeps a copy: astronomical.xsa.before_urania.");
    if (g_gains_written)
        ImGui::TextColored(ImVec4(0.5f, 1, 0.5f, 1), "Written. Restart X-Plane to see the change.");
    if (!g_gains_msg.empty() && g_gains_ok)
        ImGui::TextColored(ImVec4(1, 0.5f, 0.3f, 1), "%s", g_gains_msg.c_str());
}

void ui_info()
{
    if (!ImGui::CollapsingHeader("Moon and sun"))
        return;
    float nits = g_nits.get();
    ImGui::Text("Moon elevation %.1f deg   illumination %.0f %%", g_moon_pitch.get(), 100.0f * g_moon_illum.get());
    ImGui::Text("Sun elevation  %.1f deg", g_sun_pitch.get());
    if (!std::isnan(nits) && std::fabs(nits - kMoonNits) > 0.5f)
        ImGui::TextColored(ImVec4(1, 0.85f, 0.3f, 1), "moon/nits %.0f (shader calibrated for %.0f)", nits, kMoonNits);
    else
        ImGui::Text("moon/nits %.0f", nits);
    ImGui::TextDisabled("Engine light green: moon %.3g   sun %.3g", g_mon_amb.get(), g_sun_amb.get());
}

void ui_tests()
{
    if (!ImGui::CollapsingHeader("Haze test (not saved)"))
        return;
    ImGui::TextDisabled("X-Plane values come back with Reset or when the plugin is off.");
    for (TestRow& t : g_tests) {
        ImGui::PushID(t.ref.name);
        if (!t.ref.ref) {
            ImGui::TextDisabled("%s: dataref not found", t.label);
            ImGui::PopID();
            continue;
        }
        if (!ImGui::IsAnyItemActive() || !t.ref.changed)
            t.value = static_cast<float>(t.ref.get());
        ImGui::SetNextItemWidth(-200.0f);
        if (ImGui::SliderFloat("##v", &t.value, t.min, t.max, t.format,
                               t.log_scale ? ImGuiSliderFlags_Logarithmic : ImGuiSliderFlags_None))
            t.ref.set(t.value);
        ImGui::SameLine();
        ImGui::BeginDisabled(!t.ref.changed);
        if (ImGui::SmallButton("Reset"))
            t.ref.restore();
        ImGui::EndDisabled();
        ImGui::SameLine();
        ImGui::TextUnformatted(t.label);
        ImGui::PopID();
    }
}

#endif  // URANIA_DEV

void build_window()
{
    ui_sky();
    ui_cloud();
    ui_star_light();
#if URANIA_DEV
    ui_gains();
    ui_info();
    ui_tests();
#endif
    ImGui::Separator();
    if (ImGui::Button("Log values"))
        log_values();
    ImGui::SameLine();
    ImGui::TextDisabled("Urania %s", URANIA_VERSION);
}

// =====================================================================================
// 6. MENU AND COMMANDS
// =====================================================================================
enum Action { kWindow = 1, kToggle, kBrighter, kDimmer, kLog, kRestore };

void* item_ref(int action) { return reinterpret_cast<void*>(static_cast<intptr_t>(action)); }

void update_menu()
{
    if (!g_menu)
        return;
    XPLMCheckMenuItem(g_menu, g_idx_window, g_window && g_window->visible() ? xplm_Menu_Checked : xplm_Menu_Unchecked);
    XPLMCheckMenuItem(g_menu, g_idx_on, g_on ? xplm_Menu_Checked : xplm_Menu_Unchecked);
}

void show_window(bool visible)
{
    if (!g_window)
        g_window.reset(new ImguiWindow("Urania", 520, URANIA_DEV ? 700 : 320, build_window));
    g_window->set_visible(visible);
#if URANIA_DEV
    if (visible)
        load_gains();
#endif
}

void do_action(int action)
{
    switch (action) {
    case kWindow: show_window(!(g_window && g_window->visible())); break;
    case kRestore:
        // Ask in the window first: a menu click must not change files at once.
        g_confirm_restore = true;
        g_open_sky = true;
        show_window(true);
        update_menu();
        return;
    case kToggle: g_on = !g_on; break;
    case kBrighter: g_cloud = kCloudSteps[std::min(cloud_step(g_cloud) + 1, kCloudStepCount - 1)]; break;
    case kDimmer: g_cloud = kCloudSteps[std::max(cloud_step(g_cloud) - 1, 0)]; break;
    case kLog: log_values(); return;
    default: return;
    }
    if (action != kWindow) {
        apply("menu");
        save_prefs();
    }
    update_menu();
}

void menu_handler(void* /*menu_ref*/, void* ref) { do_action(static_cast<int>(reinterpret_cast<intptr_t>(ref))); }

void build_menu()
{
    int parent = XPLMAppendMenuItem(XPLMFindPluginsMenu(), "Urania", nullptr, 0);
    g_menu = XPLMCreateMenu("Urania", XPLMFindPluginsMenu(), parent, menu_handler, nullptr);
    g_idx_window = XPLMAppendMenuItem(g_menu, "Settings window", item_ref(kWindow), 0);
    g_idx_on = XPLMAppendMenuItem(g_menu, "Cloud moonlight on", item_ref(kToggle), 0);
    XPLMAppendMenuSeparator(g_menu);
    XPLMAppendMenuItem(g_menu, "Log values", item_ref(kLog), 0);
    XPLMAppendMenuSeparator(g_menu);
    XPLMAppendMenuItem(g_menu, "Restore X-Plane stock sky...", item_ref(kRestore), 0);
    update_menu();
}

struct Command {
    const char* name;
    const char* description;
    int action;
    XPLMCommandRef ref;
};
Command g_cmds[] = {
    {"urania/window", "Urania: show or hide the settings window", kWindow, nullptr},
    {"urania/toggle", "Urania: cloud moonlight on or off", kToggle, nullptr},
    {"urania/brighter", "Urania: cloud moonlight one step brighter (x2)", kBrighter, nullptr},
    {"urania/dimmer", "Urania: cloud moonlight one step dimmer (/2)", kDimmer, nullptr},
};

int command_handler(XPLMCommandRef /*cmd*/, XPLMCommandPhase phase, void* refcon)
{
    if (phase == xplm_CommandBegin)
        do_action(static_cast<int>(reinterpret_cast<intptr_t>(refcon)));
    return 0;                                                                // 0 = the command is done
}

// =====================================================================================
// 7. FLIGHT LOOP: write the values 1 time after the plugin is enabled and after each load.
// =====================================================================================
const char* g_pending = "start";   // reason for the next write, nullptr = nothing to do

// X-Plane makes some private datarefs (sim/private/...) only after the plugins start (seen
// 2026-10-10: "not found" at enable, DataRefTool shows them later). Thus: look again for each
// missing dataref. A dataref found later gets the plugin values at once.
void find_missing()
{
    bool found = false;
    for (Ref* r : {&g_cloud_ref, &g_star_ref})
        if (!r->ref && r->find(false))
            found = true;
#if URANIA_DEV
    for (TestRow& t : g_tests)
        if (!t.ref.ref)
            t.ref.find(false);
#endif
    for (Info* i : {&g_nits, &g_moon_pitch, &g_moon_illum, &g_sun_pitch, &g_mon_amb, &g_sun_amb})
        if (!i->ref)
            i->find();
    if (found && !g_pending)
        g_pending = "dataref found";
}

float flight_loop(float /*since_call*/, float /*since_loop*/, int /*counter*/, void* /*refcon*/)
{
    find_missing();
    if (g_pending) {
        apply(g_pending);
        check_nits();
        g_pending = nullptr;
    }
    if (g_menu)
        update_menu();                                                       // window closed with its X button
    return 2.0f;                                                             // look again in 2 s
}

}  // namespace

// =====================================================================================
// The 5 functions that X-Plane calls. PLUGIN_API exports them from Urania.xpl.
// =====================================================================================

// X-Plane calls this function 1 time, when it loads the plugin.
PLUGIN_API int XPluginStart(char* out_name, char* out_sig, char* out_desc)
{
    std::strcpy(out_name, "Urania");
    std::strcpy(out_sig, "gus.urania");   // must be unique among all plugins
    std::strcpy(out_desc, "Urania night sky: cloud moonlight, sky darkness, sky file check and restore.");
    XPLMEnableFeature("XPLM_USE_NATIVE_PATHS", 1);

    int xp_version = 0, xplm_version = 0;
    XPLMHostApplicationID host;
    XPLMGetVersions(&xp_version, &xplm_version, &host);
    log_line("start (X-Plane %d, XPLM %d, Dear ImGui %s)", xp_version, xplm_version, IMGUI_VERSION);

    char sys[1024] = {};
    XPLMGetSystemPath(sys);
    char xpl[1024] = {};
    XPLMGetPluginInfo(XPLMGetMyID(), nullptr, xpl, nullptr, nullptr);   // .../plugins/Urania/win_x64/Urania.xpl
    g_sky = sky_paths(sys, plugin_root_from_xpl(xpl), XPLMGetDirectorySeparator());
    g_xsa_path = g_sky.xsa;
    check_sky();

    for (Command& c : g_cmds) {
        c.ref = XPLMCreateCommand(c.name, c.description);
        XPLMRegisterCommandHandler(c.ref, command_handler, 1, item_ref(c.action));
    }
    load_prefs();
#if URANIA_DEV
    load_gains();
#endif
    build_menu();
    return 1;
}

// X-Plane calls this function 1 time, when it unloads the plugin.
PLUGIN_API void XPluginStop()
{
    for (Command& c : g_cmds)
        if (c.ref)
            XPLMUnregisterCommandHandler(c.ref, command_handler, 1, item_ref(c.action));
    g_window.reset();
    if (g_menu)
        XPLMDestroyMenu(g_menu);
    g_menu = nullptr;
    log_line("stop");
}

// X-Plane calls this function when it enables the plugin.
PLUGIN_API int XPluginEnable()
{
    g_cloud_ref.find();
    g_star_ref.find();
#if URANIA_DEV
    for (TestRow& t : g_tests)
        t.ref.find();
#endif
    for (Info* i : {&g_nits, &g_moon_pitch, &g_moon_illum, &g_sun_pitch, &g_mon_amb, &g_sun_amb})
        i->find();
    g_pending = "start";
    XPLMRegisterFlightLoopCallback(flight_loop, -1.0f, nullptr);
    log_line("enable");
    return 1;
}

// X-Plane calls this function when it disables the plugin.
PLUGIN_API void XPluginDisable()
{
    XPLMUnregisterFlightLoopCallback(flight_loop, nullptr);
    if (g_window)
        g_window->set_visible(false);
    restore_all();
    log_line("disable");
}

// X-Plane sends a message after each aircraft, airport or scenery load. Write the values again.
PLUGIN_API void XPluginReceiveMessage(XPLMPluginID /*from*/, int message, void* param)
{
    if (message == XPLM_MSG_PLANE_LOADED && param == nullptr)   // param 0 = the user aircraft
        g_pending = "aircraft loaded";
    else if (message == XPLM_MSG_AIRPORT_LOADED)
        g_pending = "airport loaded";
    else if (message == XPLM_MSG_SCENERY_LOADED)
        g_pending = "scenery loaded";
}
