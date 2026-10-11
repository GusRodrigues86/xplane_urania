// =====================================================================================
// sky_fragment.glsl - Night sky mod, fragment stage (astronomical stage 7).
//
// Urania (engine/shaders.py) adds "#version 460" and the settings block (@SETTINGS@).
// This stage needs no stock declarations. It replaces the full stock stage 7.
//
// Each sprite pixel gets: brightness x profile x color.
//   Star:      flat dot when small, soft glow exp(-4 r^2) when larger than 1.5 px.
//   Haze blob: Gaussian exp(-4.5 r^2) (sigma = 1/3 of the radius = diameter / 6).
// r = 0 at the sprite center, r = 1 at the sprite edge.
// =====================================================================================

layout(location = 0) in float v_L;
layout(location = 1) in vec3 v_col;
layout(location = 2) in float v_size;
layout(location = 3) flat in int v_kind;
layout(location = 4) flat in vec3 v_haze;
layout(location = 0) out vec4 data_out0;
layout(location = 6) flat in int v_eye;

// @SETTINGS@

void main()
{
    vec2 d = gl_PointCoord * 2.0 - 1.0;                  // -1..1 across the sprite
    if (v_kind == 1) d = d * v_haze.x - v_haze.yz;       // haze: distance from the true blob center
    float r2 = dot(d, d);
    float glow = exp(-4.0 * r2) * step(r2, 1.0);
    float prof = (v_kind == 1) ? exp(-4.5 * r2) * step(r2, 1.0)
                               : mix(1.0, glow, smoothstep(1.5, 3.5, v_size));
    // Haze: a small noise breaks the 8-bit banding rings (interleaved gradient noise).
    float ign = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715))));
    if (v_kind == 1) prof *= 1.0 + DITHER * (ign - 0.5);
    data_out0 = vec4(v_L * prof * v_col, 0.0);
}
