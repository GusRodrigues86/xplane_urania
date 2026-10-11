// =====================================================================================
// xsa_gains.cpp - Read and change the sky gains inside a built astronomical.xsa. See xsa_gains.h.
//
// ZIP: the code reads the central directory, finds astronomical_6.spv and astronomical_8.spv,
// and checks that they are stored (method 0). After a change, it writes the new CRC-32 into the
// local header and the central directory entry. Nothing else in the file changes.
// SPIR-V: OpDecorate <id> SpecId <n> gives the ID of each constant. OpSpecConstant <type> <id>
// <value> holds the 32-bit float value.
// =====================================================================================
#include "xsa_gains.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <vector>

#if IBM
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#endif

namespace {

const char* const kStages[] = {"astronomical_6.spv", "astronomical_8.spv"};

uint32_t rd16(const std::vector<uint8_t>& b, size_t o) { return b[o] | (b[o + 1] << 8); }
uint32_t rd32(const std::vector<uint8_t>& b, size_t o)
{
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (static_cast<uint32_t>(b[o + 3]) << 24);
}
void wr32(std::vector<uint8_t>& b, size_t o, uint32_t v)
{
    for (int i = 0; i < 4; ++i)
        b[o + i] = static_cast<uint8_t>(v >> (8 * i));
}

uint32_t crc32(const uint8_t* p, size_t n)
{
    static uint32_t table[256];
    static bool ready = false;
    if (!ready) {
        for (uint32_t i = 0; i < 256; ++i) {
            uint32_t c = i;
            for (int k = 0; k < 8; ++k)
                c = (c & 1) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
            table[i] = c;
        }
        ready = true;
    }
    uint32_t c = 0xFFFFFFFFu;
    for (size_t i = 0; i < n; ++i)
        c = table[(c ^ p[i]) & 0xFF] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

bool read_file(const std::string& path, std::vector<uint8_t>& out)
{
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f)
        return false;
    std::fseek(f, 0, SEEK_END);
    long n = std::ftell(f);
    std::fseek(f, 0, SEEK_SET);
    out.resize(n > 0 ? static_cast<size_t>(n) : 0);
    bool ok = n > 0 && std::fread(out.data(), 1, out.size(), f) == out.size();
    std::fclose(f);
    return ok;
}

bool write_file(const std::string& path, const std::vector<uint8_t>& data)
{
    FILE* f = std::fopen(path.c_str(), "wb");
    if (!f)
        return false;
    bool ok = std::fwrite(data.data(), 1, data.size(), f) == data.size();
    ok = (std::fclose(f) == 0) && ok;
    return ok;
}

bool replace_file(const std::string& from, const std::string& to)
{
#if IBM
    return MoveFileExA(from.c_str(), to.c_str(), MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
#else
    return std::rename(from.c_str(), to.c_str()) == 0;
#endif
}

// One stored ZIP entry: where its data is, and where its 2 CRC fields are.
struct Entry {
    size_t data = 0, size = 0, crc_local = 0, crc_central = 0;
};

bool find_entry(const std::vector<uint8_t>& b, const char* name, Entry& e, std::string& error)
{
    if (b.size() < 22) {
        error = "file too small for a ZIP file";
        return false;
    }
    size_t eocd = std::string::npos;
    for (size_t i = b.size() - 22 + 1; i-- > 0 && b.size() - i < 22 + 65536;)
        if (rd32(b, i) == 0x06054b50u) {
            eocd = i;
            break;
        }
    if (eocd == std::string::npos) {
        error = "not a ZIP file (no end record)";
        return false;
    }
    size_t count = rd16(b, eocd + 10), cd = rd32(b, eocd + 16), p = cd;
    for (size_t k = 0; k < count; ++k) {
        if (p + 46 > b.size() || rd32(b, p) != 0x02014b50u) {
            error = "damaged ZIP central directory";
            return false;
        }
        size_t method = rd16(b, p + 10), csize = rd32(b, p + 20), usize = rd32(b, p + 24);
        size_t nlen = rd16(b, p + 28), xlen = rd16(b, p + 30), clen = rd16(b, p + 32), local = rd32(b, p + 42);
        if (p + 46 + nlen > b.size()) {
            error = "damaged ZIP central directory";
            return false;
        }
        std::string entry_name(reinterpret_cast<const char*>(&b[p + 46]), nlen);
        if (entry_name == name) {
            if (method != 0 || csize != usize) {
                error = std::string(name) + " is compressed: this astronomical.xsa has no plugin gains (old build). "
                                            "Run the Urania app again.";
                return false;
            }
            if (local + 30 > b.size() || rd32(b, local) != 0x04034b50u) {
                error = "damaged ZIP local header";
                return false;
            }
            e.data = local + 30 + rd16(b, local + 26) + rd16(b, local + 28);
            e.size = usize;
            e.crc_local = local + 14;
            e.crc_central = p + 16;
            if (e.data + e.size > b.size()) {
                error = "damaged ZIP entry";
                return false;
            }
            return true;
        }
        p += 46 + nlen + xlen + clen;
    }
    error = std::string("no ") + name + " in the file";
    return false;
}

// SPIR-V: byte offset of the value word of each specialization constant, by SpecId.
bool find_spec_values(const std::vector<uint8_t>& b, const Entry& e, std::map<int, size_t>& out, std::string& error)
{
    if (e.size < 20 || e.size % 4 != 0 || rd32(b, e.data) != 0x07230203u) {
        error = "not a SPIR-V program";
        return false;
    }
    std::map<uint32_t, int> spec_of_id;        // result id -> SpecId
    std::map<uint32_t, size_t> value_of_id;    // result id -> byte offset of the value
    size_t p = e.data + 20, end = e.data + e.size;
    while (p < end) {
        uint32_t w = rd32(b, p);
        uint32_t words = w >> 16, op = w & 0xFFFF;
        if (words == 0 || p + 4 * words > end) {
            error = "damaged SPIR-V program";
            return false;
        }
        if (op == 71 && words >= 4 && rd32(b, p + 8) == 1)                  // OpDecorate <id> SpecId <n>
            spec_of_id[rd32(b, p + 4)] = static_cast<int>(rd32(b, p + 12));
        else if (op == 50 && words == 4)                                     // OpSpecConstant <type> <id> <32-bit value>
            value_of_id[rd32(b, p + 8)] = p + 12;
        p += 4 * words;
    }
    for (auto& kv : spec_of_id) {
        auto v = value_of_id.find(kv.first);
        if (v != value_of_id.end())
            out[kv.second] = v->second;
    }
    for (int g = 0; g < kGainCount; ++g)
        if (!out.count(kGainSpecId[g])) {
            error = "this astronomical.xsa has no plugin gains (old build). Run the Urania app again.";
            return false;
        }
    return true;
}

float as_float(uint32_t w)
{
    float f;
    std::memcpy(&f, &w, 4);
    return f;
}

uint32_t as_word(float f)
{
    uint32_t w;
    std::memcpy(&w, &f, 4);
    return w;
}

}  // namespace

bool read_sky_gains(const std::string& xsa_path, SkyGains& out, std::string& error)
{
    std::vector<uint8_t> b;
    if (!read_file(xsa_path, b)) {
        error = "cannot read " + xsa_path;
        return false;
    }
    Entry e;
    std::map<int, size_t> values;
    if (!find_entry(b, kStages[0], e, error) || !find_spec_values(b, e, values, error))
        return false;
    for (int g = 0; g < kGainCount; ++g)
        out.value[g] = as_float(rd32(b, values[kGainSpecId[g]]));
    auto haze = values.find(kHazeEmissiveSpecId);
    out.haze_emissive = (haze != values.end()) ? as_float(rd32(b, haze->second)) : 0.0f;
    return true;
}

bool write_sky_gains(const std::string& xsa_path, const SkyGains& gains, std::string& error)
{
    std::vector<uint8_t> b;
    if (!read_file(xsa_path, b)) {
        error = "cannot read " + xsa_path;
        return false;
    }
    std::vector<uint8_t> original = b;
    for (const char* stage : kStages) {
        Entry e;
        std::map<int, size_t> values;
        if (!find_entry(b, stage, e, error) || !find_spec_values(b, e, values, error))
            return false;
        for (int g = 0; g < kGainCount; ++g)
            wr32(b, values[kGainSpecId[g]], as_word(gains.value[g]));
        uint32_t crc = crc32(&b[e.data], e.size);
        wr32(b, e.crc_local, crc);
        wr32(b, e.crc_central, crc);
    }
    if (b == original)
        return true;
    std::string backup = xsa_path + ".before_urania";
    std::vector<uint8_t> probe;
    if (!read_file(backup, probe) && !write_file(backup, original)) {
        error = "cannot write the backup " + backup;
        return false;
    }
    std::string tmp = xsa_path + ".tmp";
    if (!write_file(tmp, b) || !replace_file(tmp, xsa_path)) {
        std::remove(tmp.c_str());
        error = "cannot write " + xsa_path;
        return false;
    }
    return true;
}
