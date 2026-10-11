// =====================================================================================
// xsa_gains.h - Read and change the sky gains inside a built astronomical.xsa.
//
// The Urania app (engine/shaders.py) writes 4 gains as SPIR-V specialization constants (IDs 200-203) into the
// star stages 6 and 8 (ID 204 = HAZE_EMISSIVE, read only here). The script stores these
// 2 stages without compression. X-Plane does not set specialization constants with these IDs,
// so the GPU uses the default value in the file.
// This code finds the 4 values and writes new ones in place. The file size does not change.
// X-Plane reads the shader file when it starts: a change shows after an X-Plane restart.
//
// GLOSSARY
//   .xsa                 ZIP file with 9 SPIR-V programs (astronomical_0.spv ... _8.spv).
//   SPIR-V               binary GPU program format (32-bit words).
//   specialization       a constant in a SPIR-V program with an ID. The default value is in the
//   constant             program. The program creator can replace it; X-Plane does not.
// =====================================================================================
#pragma once

#include <string>

enum SkyGain { kGainStar = 0, kGainMilkyWay, kGainNebula, kGainGalaxy, kGainCount };

struct SkyGains {
    float value[kGainCount] = {0.0f, 0.0f, 0.0f, 0.0f};
    // Fixed star light for the haze (SpecId 204, read only). The sky darkness slider then changes the
    // stars only. 0 or less = the haze follows gain_photometric (old build, or HAZE_EMISSIVE=0).
    float haze_emissive = 0.0f;
};

// SPIR-V specialization constant IDs (must agree with GAIN_SPEC_IDS in src/urania/engine/spirv.py;
// tests/test_shaders.py checks this).
const int kGainSpecId[kGainCount] = {200, 201, 202, 203};
const int kHazeEmissiveSpecId = 204;
// Defaults of the tested build (DEFAULT_SETTINGS in src/urania/engine/shaders.py).
const float kGainDefault[kGainCount] = {0.35f, 3.0f, 40.0f, 40.0f};

// Read the gains from the file. Return false and set error if the file is not a Urania build
// with gains (example: an old build, or the X-Plane original).
bool read_sky_gains(const std::string& xsa_path, SkyGains& out, std::string& error);

// Write the gains into the file. Before the first change, the code copies the file to
// <xsa_path>.before_urania (only if that copy does not exist). Return false and set error on failure.
bool write_sky_gains(const std::string& xsa_path, const SkyGains& gains, std::string& error);
