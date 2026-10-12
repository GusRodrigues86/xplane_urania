// =====================================================================================
// test_core.cpp - Unit tests for urania_core (xsa_gains, sky_files). No X-Plane needed.
//
//   urania_tests <fixtures dir>              run all tests (CTest does this)
//   urania_tests --read-gains <xsa>          print "SpecId value" lines (tests/test_plugin_contract.py)
//   urania_tests --write-gains <xsa> a b c d write 4 gains into the file
// =====================================================================================
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>

#include "sky_files.h"
#include "xsa_gains.h"

namespace fs = std::filesystem;

namespace {

int g_failures = 0;
int g_checks = 0;

#define CHECK(cond)                                                                   \
    do {                                                                              \
        ++g_checks;                                                                   \
        if (!(cond)) {                                                                \
            ++g_failures;                                                             \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);      \
        }                                                                             \
    } while (0)

bool near(float a, float b) { return std::fabs(a - b) < 1e-6f; }

std::string read_all(const fs::path& p)
{
    std::ifstream f(p, std::ios::binary);
    return std::string(std::istreambuf_iterator<char>(f), std::istreambuf_iterator<char>());
}

void write_all(const fs::path& p, const std::string& data)
{
    fs::create_directories(p.parent_path());
    std::ofstream f(p, std::ios::binary);
    f << data;
}

std::string sep() { return std::string(1, static_cast<char>(fs::path::preferred_separator)); }

// --- xsa_gains -------------------------------------------------------------------------

void test_read_gains(const fs::path& fx)
{
    SkyGains g;
    std::string err;
    CHECK(read_sky_gains((fx / "gains_stored.xsa").string(), g, err));
    CHECK(near(g.value[kGainStar], 0.35f));
    CHECK(near(g.value[kGainMilkyWay], 3.0f));
    CHECK(near(g.value[kGainNebula], 40.0f));
    CHECK(near(g.value[kGainGalaxy], 25.0f));
    CHECK(near(g.haze_emissive, 0.0f));
}

void test_read_gains_errors(const fs::path& fx)
{
    SkyGains g;
    std::string err;
    CHECK(!read_sky_gains((fx / "gains_deflated.xsa").string(), g, err));
    CHECK(err.find("compressed") != std::string::npos);
    err.clear();
    CHECK(!read_sky_gains((fx / "no_gains.xsa").string(), g, err));
    CHECK(err.find("no plugin gains") != std::string::npos);
    err.clear();
    CHECK(!read_sky_gains((fx / "missing.xsa").string(), g, err));
    CHECK(!err.empty());
}

void test_write_gains(const fs::path& fx, const fs::path& tmp)
{
    fs::path xsa = tmp / "astronomical.xsa";
    fs::copy_file(fx / "gains_stored.xsa", xsa, fs::copy_options::overwrite_existing);
    std::string original = read_all(xsa);
    SkyGains g;
    g.value[kGainStar] = 0.5f;
    g.value[kGainMilkyWay] = 2.0f;
    g.value[kGainNebula] = 15.0f;
    g.value[kGainGalaxy] = 60.0f;
    std::string err;
    CHECK(write_sky_gains(xsa.string(), g, err));
    SkyGains back;
    CHECK(read_sky_gains(xsa.string(), back, err));
    CHECK(near(back.value[kGainStar], 0.5f) && near(back.value[kGainGalaxy], 60.0f));
    CHECK(fs::file_size(xsa) == original.size());                    // values change in place
    fs::path backup = tmp / "astronomical.xsa.before_urania";
    CHECK(read_all(backup) == original);
    // A second write must not replace the first backup.
    g.value[kGainStar] = 0.25f;
    CHECK(write_sky_gains(xsa.string(), g, err));
    CHECK(read_all(backup) == original);
}

// --- sky_files -------------------------------------------------------------------------

struct Layout {
    fs::path root, plugin;
    SkyPaths paths;
};

Layout make_layout(const fs::path& fx, const fs::path& tmp)
{
    Layout l;
    l.root = tmp / "X-Plane 12";
    l.plugin = l.root / "Resources" / "plugins" / "Urania";
    l.paths = sky_paths(l.root.string() + sep(), l.plugin.string() + sep(), sep().c_str());
    fs::create_directories(fs::path(l.paths.xsa).parent_path());
    fs::copy_file(fx / "gains_stored.xsa", l.paths.xsa, fs::copy_options::overwrite_existing);
    write_all(l.paths.dat, std::string(1000, 'u'));
    write_all(l.paths.backup_xsa, "stock shader");
    write_all(l.paths.backup_dat, "stock stars");
    write_all(l.paths.manifest, "urania 1.0.0\nxsa_sha256 abc\nxsa_size " + std::to_string(fs::file_size(l.paths.xsa)) +
                                    "\ndat_sha256 def\ndat_size 1000\n");
    return l;
}

void test_sky_paths()
{
    SkyPaths p = sky_paths("/xp/", "/xp/Resources/plugins/Urania/", "/");
    CHECK(p.xsa == "/xp/Resources/shaders/bin/spv/astronomical.xsa");
    CHECK(p.dat == "/xp/Resources/default data/earth_astro.dat");
    CHECK(p.manifest == "/xp/Resources/plugins/Urania/install.txt");
    CHECK(p.backup_dat == "/xp/Resources/plugins/Urania/backup/earth_astro.dat");
}

void test_plugin_root()
{
    CHECK(plugin_root_from_xpl("/xp/Resources/plugins/Urania/lin_x64/Urania.xpl") == "/xp/Resources/plugins/Urania/");
    CHECK(plugin_root_from_xpl("C:\\X\\plugins\\Urania\\win_x64\\Urania.xpl") == "C:\\X\\plugins\\Urania\\");
    CHECK(plugin_root_from_xpl("Urania.xpl").empty());
}

void test_install_info(const fs::path& tmp)
{
    InstallInfo info;
    std::string err;
    write_all(tmp / "good.txt", "urania 1.0.0\nxsa_size 60966\ndat_size 1615523\n");
    CHECK(read_install_info((tmp / "good.txt").string(), info, err));
    CHECK(info.version == "1.0.0" && info.xsa_size == 60966 && info.dat_size == 1615523);
    CHECK(info.moon == -1);                                             // 1.0.0 zips have no moon line
    write_all(tmp / "moon.txt", "urania 1.0.1\nxsa_size 1\ndat_size 2\nmoon 1\n");
    CHECK(read_install_info((tmp / "moon.txt").string(), info, err));
    CHECK(info.moon == 1);
    write_all(tmp / "nomoon.txt", "urania 1.0.1\nxsa_size 1\ndat_size 2\nmoon 0\n");
    CHECK(read_install_info((tmp / "nomoon.txt").string(), info, err) && info.moon == 0);
    write_all(tmp / "bad.txt", "hello world\n");
    CHECK(!read_install_info((tmp / "bad.txt").string(), info, err));
    CHECK(!read_install_info((tmp / "none.txt").string(), info, err));
}

void test_check_sky(const fs::path& fx, const fs::path& tmp)
{
    Layout l = make_layout(fx, tmp / "check");
    CHECK(check_sky_files(l.paths).state == SkyState::kInstalled);

    write_all(l.paths.dat, std::string(999, 'x'));                      // an X-Plane update replaced it
    SkyCheck c = check_sky_files(l.paths);
    CHECK(c.state == SkyState::kReplaced);
    CHECK(c.detail.find("earth_astro.dat") != std::string::npos);

    write_all(l.paths.dat, std::string(1000, 'u'));
    fs::copy_file(fx / "no_gains.xsa", l.paths.xsa, fs::copy_options::overwrite_existing);
    write_all(l.paths.manifest, "urania 1.0.0\nxsa_size " + std::to_string(fs::file_size(l.paths.xsa)) + "\ndat_size 1000\n");
    CHECK(check_sky_files(l.paths).state == SkyState::kReplaced);       // same size, but no gains

    fs::remove(l.paths.manifest);
    CHECK(check_sky_files(l.paths).state == SkyState::kNoManifest);
}

void test_restore(const fs::path& fx, const fs::path& tmp)
{
    Layout l = make_layout(fx, tmp / "restore");
    std::string err;
    CHECK(restore_stock_sky(l.paths, err));
    CHECK(read_all(l.paths.xsa) == "stock shader");
    CHECK(read_all(l.paths.dat) == "stock stars");
    CHECK(!fs::exists(l.paths.xsa + ".tmp"));
    CHECK(check_sky_files(l.paths).state == SkyState::kReplaced);

    fs::remove(l.paths.backup_dat);
    err.clear();
    CHECK(!restore_stock_sky(l.paths, err));
    CHECK(err.find("no backup") != std::string::npos);
}

int read_gains_cli(const char* path)
{
    SkyGains g;
    std::string err;
    if (!read_sky_gains(path, g, err)) {
        std::fprintf(stderr, "%s\n", err.c_str());
        return 1;
    }
    for (int i = 0; i < kGainCount; ++i)
        std::printf("%d %.9g\n", kGainSpecId[i], g.value[i]);
    std::printf("%d %.9g\n", kHazeEmissiveSpecId, g.haze_emissive);
    return 0;
}

int write_gains_cli(int argc, char** argv)
{
    if (argc != 7)
        return 2;
    SkyGains g;
    for (int i = 0; i < kGainCount; ++i)
        g.value[i] = static_cast<float>(std::atof(argv[3 + i]));
    std::string err;
    if (!write_sky_gains(argv[2], g, err)) {
        std::fprintf(stderr, "%s\n", err.c_str());
        return 1;
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv)
{
    if (argc == 3 && std::string(argv[1]) == "--read-gains")
        return read_gains_cli(argv[2]);
    if (argc >= 2 && std::string(argv[1]) == "--write-gains")
        return write_gains_cli(argc, argv);
    if (argc != 2) {
        std::fprintf(stderr, "usage: urania_tests <fixtures dir>\n");
        return 2;
    }
    fs::path fx = argv[1];
    fs::path tmp = fs::temp_directory_path() / "urania_core_tests";
    fs::remove_all(tmp);
    fs::create_directories(tmp);

    test_read_gains(fx);
    test_read_gains_errors(fx);
    test_write_gains(fx, tmp);
    test_sky_paths();
    test_plugin_root();
    test_install_info(tmp);
    test_check_sky(fx, tmp);
    test_restore(fx, tmp);

    fs::remove_all(tmp);
    std::printf("%d checks, %d failures\n", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
