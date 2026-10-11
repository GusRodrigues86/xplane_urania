// =====================================================================================
// sky_vertex.glsl - Night sky mod, vertex stage (astronomical stages 6 and 8).
//
// Urania (engine/shaders.py) builds the full vertex shader from 3 parts:
//   1. The stock declarations (uniform blocks, sampler, a_vertex). The script reads them
//      from YOUR X-Plane file at build time. This repository does not contain X-Plane code.
//   2. The settings block (@SETTINGS@) and the star color table (@STAR_RGB@).
//   3. This file.
//
// The script also defines 3 names for the stock uniform blocks:
//   XFORM = u_transform_block_fat (view, projection and instance data)
//   ASTRO = u_astronomical_data   (u_light_emissive)
//   ENV   = u_environment_data    (u_exposure_scale)
//
// Each row of earth_astro.dat arrives as a_vertex = (x, y, z, magnitude field).
// The magnitude field carries a code in its decimals. See NIGHT_SKY_ENCODING.md.
// =====================================================================================

layout(location = 6) flat out int v_eye;      // view index (stock output, the fragment stage reads it)
layout(location = 0) out float v_L;           // brightness (stock output)
layout(location = 1) out vec3 v_col;          // color
layout(location = 2) out float v_size;        // sprite size in pixels
layout(location = 3) flat out int v_kind;     // 0 = star, 1 = haze blob
layout(location = 4) flat out vec3 v_haze;    // haze: sprite size ratio, true center shift (x, y)

// @SETTINGS@

// Haze color classes (linear RGB, luminance near 1).
const vec3 HAZE_RGB[4] = vec3[4](
    HAZE_RGB_0,     // 0 Milky Way and airglow
    HAZE_RGB_1,     // 1 H-alpha emission nebula
    HAZE_RGB_2,     // 2 nebula core, reflection nebula, planetary nebula
    HAZE_RGB_3);    // 3 galaxy, globular cluster

// Star colors: index = color code k (0 = white, 1..89 = B-V -0.40..2.00). Luminance 1.
// @STAR_RGB@

void main()
{
    // --- Stock part: instance -> view, position ----------------------------------
    // X-Plane draws the sky once for each view. The instance number selects the view.
    int inst = gl_InstanceIndex - gl_BaseInstance;
    gl_ViewportIndex = inst % XFORM.u_viewport_count;
    gl_Layer = (inst % XFORM.u_layer_count) + XFORM.u_layer_offset;
    int view = inst % XFORM.u_transform_count;
    vec4 pos = vec4(a_vertex.xyz - XFORM.u_mv_offset, 1.0);
    gl_Position = XFORM.mvp_matrix[view] * pos;
    v_eye = view;

    // --- Mod part: decode the field ----------------------------------------------
    // t = field x 100. n = integer part (+0.005 protects against float32 error).
    // k = 3rd and 4th decimals. k >= 90 is a haze blob, k <= 89 is a star color code.
    float scale = 1.0;      // brightness factor
    float fade = 1.0;       // 0 = do not draw this row in this view
    v_haze = vec3(1.0, 0.0, 0.0);
    float t = a_vertex.w * 100.0;
    float n = floor(t + 0.005);
    int k = clamp(int(round((t - n) * 100.0)), 0, 99);

    if (k >= 90)
    {
        // --- Haze blob ------------------------------------------------------------
        // code = (k - 90) * 10 + c = color * 25 + size. c = 2nd decimal.
        int c = int(n - 10.0 * floor(n / 10.0) + 0.5) % 10;
        int code = (k - 90) * 10 + c;
        float mag = (n - float(c)) * 0.01;                         // true magnitude (0.1 step)
        float diam = radians(0.1 * pow(1.25, float(code % 25)));   // diameter in radians
        mat4 P = XFORM.projection_matrix[view];

        // A flat (rectilinear) projection stretches the sky toward the screen edges by (1 + tan^2).
        // Grow the sprite by the same factor. Keep the brightness of the unstretched sprite (S0).
        vec2 ndc = gl_Position.xy / max(gl_Position.w, 1e-6);
        vec2 tn = ndc / vec2(abs(P[0][0]), abs(P[1][1]));          // tan of the view angle (x, y)
        float stretch = (1.0 + dot(tn, tn)) * EDGE_STRETCH + (1.0 - EDGE_STRETCH);
        // 0.5 * VIEWPORT_H * P[1][1] = pixels per radian at the screen center.
        float S = clamp(diam * 0.5 * VIEWPORT_H * abs(P[1][1]) * stretch, 1.0, MAX_SPRITE);
        float S0 = S / stretch;

        v_kind = 1;
        v_size = S;
        v_col = max(mix(vec3(1.0), HAZE_RGB[code / 25], HAZE_SAT), vec3(0.0));
        // 1. exp(0.921034 (field - mag)) removes the code digits from the stock brightness.
        // 2. The gain sets the brightness of each class: 0 Milky Way, 1-2 nebulae, 3 galaxies and clusters.
        // 3. 0.1728 S0^2 = area of the profile exp(-4.5 r^2): the blob keeps the total light of 'mag'.
        int cls = code / 25;
        float gain = (cls == 0) ? MW_GAIN : ((cls == 3) ? GALAXY_GAIN : NEBULA_GAIN);
        scale = exp(0.921034 * (a_vertex.w - mag)) * gain / (0.1728 * S0 * S0);

        // The GPU drops a point sprite if its center is outside the view. A large blob with its center
        // just outside the view then disappears. Thus: move the center inside the view (CLAMP_NDC),
        // make the sprite larger, and send the true center shift to the fragment stage (v_haze).
        vec2 ndc_c = clamp(ndc, vec2(-CLAMP_NDC), vec2(CLAMP_NDC));
        vec2 sh = (ndc - ndc_c) * 0.5 * vec2(VIEWPORT_H * abs(P[1][1] / P[0][0]), VIEWPORT_H);
        sh.y *= -sign(P[1][1]);                                    // NDC up -> window rows (Vulkan y points down)
        float R = 0.5 * S;
        if (gl_Position.w <= 0.0 || max(abs(sh.x), abs(sh.y)) > R)
        {
            // The blob is fully outside this view, or behind the camera. Do not draw it.
            // (Large invisible sprites cost 10x GPU time in an earlier version.)
            fade = 0.0;
            gl_Position = vec4(2.0, 2.0, 2.0, 1.0);                // outside the clip volume
            v_size = 1.0;
            v_haze = vec3(1.0, 0.0, 0.0);
        }
        else
        {
            float S2 = min(S + 2.0 * max(abs(sh.x), abs(sh.y)), MAX_SPRITE);
            gl_Position.xy = ndc_c * gl_Position.w;
            v_size = S2;
            v_haze = vec3(S2 / S, sh / R);
        }
    }
    else
    {
        // --- Star -------------------------------------------------------------------
        // The color code changes the magnitude by at most 0.0089. No correction is necessary.
        v_kind = 0;
        v_col = max(mix(vec3(1.0), STAR_RGB[k], SAT), vec3(0.0));
        v_size = clamp(SIZE_BASE - SIZE_PER_MAG * a_vertex.w, SIZE_MIN, SIZE_MAX);
        scale = STAR_GAIN;
    }
    gl_PointSize = v_size;

    // --- Brightness -------------------------------------------------------------------
    // Stock brightness: 2.128e-6 lux for magnitude 0. Pogson law: exp(-0.921034 m) = 10^(-0.4 m).
    // HAZE_EMISSIVE > 0: the haze uses this fixed star light. Then the plugin "sky darkness"
    // (gain_photometric -> u_light_emissive) changes the stars only. 0 = the haze follows it too.
    float emissive = (v_kind == 1 && HAZE_EMISSIVE > 0.0) ? HAZE_EMISSIVE : ASTRO.u_light_emissive;
    v_L = 2.1281391582306241616606712341309e-06 * exp(-0.921034038066864013671875 * a_vertex.w)
        * emissive * ENV.u_exposure_scale.y;
    // The stock shader also multiplied v_L by the sky texture transparency (u_tex_skydome.w).
    // The mod does not: that texture has a dark band at the screen center (the "dark lane").
    v_L *= scale * fade;
}
