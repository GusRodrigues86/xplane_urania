// =====================================================================================
// sky_files.h - Check and restore the 2 sky files that the Urania zip installs.
//
// The Urania app writes Resources/plugins/Urania/install.txt with the size of each file it
// installed, and puts the user's original files in Resources/plugins/Urania/backup/.
// An X-Plane update can replace the 2 files with new originals. The plugin then tells the user
// to run the Urania app again. "Restore X-Plane stock sky" copies the backup files back.
//
// No XPLM calls in this file: the tests (plugin/tests) use it without X-Plane.
//
// GLOSSARY
//   sky files   astronomical.xsa (shader) and earth_astro.dat (star data).
//   manifest    install.txt: one "key value" pair per line.
// =====================================================================================
#pragma once

#include <string>

struct InstallInfo {
    std::string version;            // Urania version that made the zip
    long long xsa_size = -1;        // size of the installed astronomical.xsa
    long long dat_size = -1;        // size of the installed earth_astro.dat
};

enum class SkyState {
    kInstalled,       // the 2 files are the Urania files
    kReplaced,        // one or both files differ (probably an X-Plane update)
    kNoManifest,      // install.txt is missing or bad (not installed from a Urania zip)
};

struct SkyCheck {
    SkyState state = SkyState::kNoManifest;
    std::string detail;             // text for the log and the window
};

// Paths of the sky files inside an X-Plane folder (root ends with a separator).
struct SkyPaths {
    std::string xsa;                // <root>Resources/shaders/bin/spv/astronomical.xsa
    std::string dat;                // <root>Resources/default data/earth_astro.dat
    std::string manifest;           // <plugin>install.txt
    std::string backup_xsa;         // <plugin>backup/astronomical.xsa
    std::string backup_dat;         // <plugin>backup/earth_astro.dat
};

// xplane_root and plugin_root end with the directory separator sep.
SkyPaths sky_paths(const std::string& xplane_root, const std::string& plugin_root, const char* sep);

// Read install.txt. Return false and set error if the file is missing or bad.
bool read_install_info(const std::string& path, InstallInfo& out, std::string& error);

// Compare the installed files with install.txt (sizes) and check that the shader has the gains.
SkyCheck check_sky_files(const SkyPaths& paths);

// Copy the backup files back to their places (write .tmp, then rename). Return false and set error
// on failure. The files that X-Plane uses change only at the next X-Plane start.
bool restore_stock_sky(const SkyPaths& paths, std::string& error);

// Return the folder 2 levels above a plugin file path, with the end separator:
// ".../plugins/Urania/win_x64/Urania.xpl" -> ".../plugins/Urania/".
std::string plugin_root_from_xpl(const std::string& xpl_path);

long long file_size(const std::string& path);   // -1 if the file does not exist
