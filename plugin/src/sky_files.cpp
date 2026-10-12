// =====================================================================================
// sky_files.cpp - Check and restore the sky files. See sky_files.h.
// =====================================================================================
#include "sky_files.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "xsa_gains.h"

#if IBM
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#endif

namespace {

bool copy_file(const std::string& from, const std::string& to, std::string& error)
{
    FILE* in = std::fopen(from.c_str(), "rb");
    if (!in) {
        error = "cannot read " + from;
        return false;
    }
    std::vector<char> data;
    char buf[1 << 16];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof(buf), in)) > 0)
        data.insert(data.end(), buf, buf + n);
    bool read_ok = !std::ferror(in);
    std::fclose(in);
    if (!read_ok || data.empty()) {
        error = "cannot read " + from;
        return false;
    }
    std::string tmp = to + ".tmp";
    FILE* out = std::fopen(tmp.c_str(), "wb");
    if (!out) {
        error = "cannot write " + tmp;
        return false;
    }
    bool ok = std::fwrite(data.data(), 1, data.size(), out) == data.size();
    ok = (std::fclose(out) == 0) && ok;
#if IBM
    ok = ok && MoveFileExA(tmp.c_str(), to.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
#else
    ok = ok && std::rename(tmp.c_str(), to.c_str()) == 0;
#endif
    if (!ok) {
        std::remove(tmp.c_str());
        error = "cannot write " + to;
    }
    return ok;
}

}  // namespace

long long file_size(const std::string& path)
{
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f)
        return -1;
    long long n = -1;
    if (std::fseek(f, 0, SEEK_END) == 0) {
#if IBM
        n = _ftelli64(f);
#else
        n = static_cast<long long>(std::ftell(f));
#endif
    }
    std::fclose(f);
    return n;
}

SkyPaths sky_paths(const std::string& xplane_root, const std::string& plugin_root, const char* sep)
{
    std::string s(sep);
    SkyPaths p;
    p.xsa = xplane_root + "Resources" + s + "shaders" + s + "bin" + s + "spv" + s + "astronomical.xsa";
    p.dat = xplane_root + "Resources" + s + "default data" + s + "earth_astro.dat";
    p.manifest = plugin_root + "install.txt";
    p.backup_xsa = plugin_root + "backup" + s + "astronomical.xsa";
    p.backup_dat = plugin_root + "backup" + s + "earth_astro.dat";
    return p;
}

bool read_install_info(const std::string& path, InstallInfo& out, std::string& error)
{
    FILE* f = std::fopen(path.c_str(), "r");
    if (!f) {
        error = "no " + path;
        return false;
    }
    out = InstallInfo();
    char key[64], value[256];
    while (std::fscanf(f, "%63s %255s", key, value) == 2) {
        if (std::strcmp(key, "urania") == 0)
            out.version = value;
        else if (std::strcmp(key, "xsa_size") == 0)
            out.xsa_size = std::atoll(value);
        else if (std::strcmp(key, "dat_size") == 0)
            out.dat_size = std::atoll(value);
        else if (std::strcmp(key, "moon") == 0)
            out.moon = std::atoi(value) ? 1 : 0;
    }
    std::fclose(f);
    if (out.version.empty() || out.xsa_size <= 0 || out.dat_size <= 0) {
        error = "bad file " + path;
        return false;
    }
    return true;
}

SkyCheck check_sky_files(const SkyPaths& paths)
{
    SkyCheck c;
    InstallInfo info;
    std::string err;
    if (!read_install_info(paths.manifest, info, err)) {
        c.state = SkyState::kNoManifest;
        c.detail = err;
        return c;
    }
    c.info = info;
    std::string changed;
    if (file_size(paths.xsa) != info.xsa_size)
        changed += "astronomical.xsa";
    if (file_size(paths.dat) != info.dat_size)
        changed += changed.empty() ? "earth_astro.dat" : " and earth_astro.dat";
    SkyGains gains;
    if (changed.empty() && !read_sky_gains(paths.xsa, gains, err))
        changed = "astronomical.xsa (" + err + ")";
    if (!changed.empty()) {
        c.state = SkyState::kReplaced;
        c.detail = "replaced: " + changed + ". An X-Plane update replaces these files. Run the Urania app again.";
        return c;
    }
    c.state = SkyState::kInstalled;
    c.detail = "Urania " + info.version + " sky files installed";
    return c;
}

bool restore_stock_sky(const SkyPaths& paths, std::string& error)
{
    if (file_size(paths.backup_xsa) <= 0 || file_size(paths.backup_dat) <= 0) {
        error = "no backup files in " + paths.backup_xsa.substr(0, paths.backup_xsa.find_last_of("/\\") + 1);
        return false;
    }
    return copy_file(paths.backup_xsa, paths.xsa, error) && copy_file(paths.backup_dat, paths.dat, error);
}

std::string plugin_root_from_xpl(const std::string& xpl_path)
{
    size_t a = xpl_path.find_last_of("/\\");
    if (a == std::string::npos || a == 0)
        return std::string();
    size_t b = xpl_path.find_last_of("/\\", a - 1);
    return (b == std::string::npos) ? std::string() : xpl_path.substr(0, b + 1);
}
