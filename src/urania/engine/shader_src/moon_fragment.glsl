// =====================================================================================
// moon_fragment.glsl - Moon sky mod, fragment stage (astronomical stage 1).
//
// Urania (engine/shaders.py) keeps the stock declarations of the stage and replaces the main function.
// It adds the settings (@SETTINGS@), the aliases MASTRO and MDOME (uniform blocks), and the
// stock sky texture lookup (@STOCK_SKY@) from your own astronomical.xsa. The lookup writes
// stock_sky (rgb = sky color, w = sky transmission for the moon disk).
//
// Each pixel gets:
//   glow  moonlit sky, Krisciunas & Schaefer (1991): scatter function f(rho) x moon extinction
//         x sky scatter x moon phase. Brightness x luminance of u_light_diffuse (= moon/nits).
//         The scene light pass (cube face) gets MOON_ENV more glow.
//   disk  the moon disk. UV comes from the mesh UV map, extrapolated with a 2x2 Jacobian.
//         Stock lighting and stock normal-map math.
// Sun up: the glow is 0 and the stage draws only the moon disk (stock dome sky elsewhere).
// Output alpha = disk mask: outside the disk the glow adds to what is behind it (stars, sky).
// =====================================================================================

// @SETTINGS@

const vec3 LUMA = vec3(0.2126, 0.7152, 0.0722);

uint pcg_hash(uint v)
{
    uint st = v * 747796405u + 2891336453u;
    uint w = ((st >> ((st >> 28u) + 4u)) ^ st) * 277803737u;
    return (w >> 22u) ^ w;
}

void main()
{
    vec3 dir = normalize(v_position_eye);                 // pixel direction, eye space
    vec3 c = normalize(v_normal_eye);                     // moon center direction, eye space
    float cr = clamp(dot(dir, c), -1.0, 1.0);
    float rho = degrees(acos(cr));                        // angle from the moon
    // @STOCK_SKY@
    mat3 sk = mat3(MDOME.u_sky_inv[0].xyz, MDOME.u_sky_inv[1].xyz, MDOME.u_sky_inv[2].xyz);
    float se = clamp(normalize(sk * dir).y, -1.0, 1.0);   // sin(elevation), pixel
    float sm = clamp(normalize(sk * c).y, -1.0, 1.0);     // sin(elevation), moon
    vec3 L = MASTRO.u_light_diffuse;
    vec3 s = MASTRO.u_light_position;
    s = (dot(s, s) > 0.0) ? normalize(s) : vec3(0.0, 0.0, 1.0);
    float ss = clamp(normalize(sk * s).y, -1.0, 1.0);     // sin(elevation), sun

    // moon glow: Krisciunas & Schaefer 1991
    float f = 229086.77 * (1.06 + cr * cr) + pow(10.0, 6.15 - rho / 40.0);
    float ze = max(se, 0.0);
    float zm = max(sm, 0.0);
    float am = inversesqrt(1.0 - 0.96 * (1.0 - ze * ze));       // airmass, pixel
    float amm = inversesqrt(1.0 - 0.96 * (1.0 - zm * zm));      // airmass, moon
    float phi = 180.0 - degrees(acos(clamp(dot(c, s), -1.0, 1.0)));   // phase angle
    float phase = pow(10.0, -0.4 * (0.026 * phi + 4e-9 * phi * phi * phi * phi));
    float fade = smoothstep(-2.0, 1.0, degrees(asin(sm)));      // moon below the horizon: no glow
    float ks = f * pow(10.0, -0.4 * MOON_K_EXT * amm) * (1.0 - pow(10.0, -0.4 * MOON_K_EXT * am)) * phase * fade;
    float night = smoothstep(0.0, -0.1, ss);              // sun 0 deg -> -6 deg: glow fades in
    bool lightpass = v_ratio.x > 0.5;
    uvec2 fc = uvec2(gl_FragCoord.xy);
    float n1 = float(pcg_hash(fc.x + pcg_hash(fc.y))) * (1.0 / 4294967295.0);
    float n2 = float(pcg_hash(fc.x + pcg_hash(fc.y + 40503u))) * (1.0 / 4294967295.0);
    float dith = 1.0 + MOON_DITHER * (n1 + n2 - 1.0);    // triangle noise against banding
    vec3 glow = MOON_RGB_N * (dot(L, LUMA) * MOON_GLOW_K * ks * night * dith * (lightpass ? MOON_ENV : 1.0));

    // moon disk: UV extrapolated from the mesh UV map
    vec3 up = (abs(c.y) < 0.9) ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);
    vec3 e1 = normalize(cross(up, c));
    vec3 e2 = cross(c, e1);
    vec2 dv = vec2(dot(v_dir_wrl, e1), dot(v_dir_wrl, e2));                 // mesh disk coordinate here
    vec2 dt = vec2(dot(dir, e1), dot(dir, e2)) * (1.0 / MOON_SIN_R);        // disk coordinate of the moon point seen here
    mat2 md = mat2(dFdx(dv), dFdy(dv));
    mat2 mu = mat2(dFdx(v_texcoord0), dFdy(v_texcoord0));
    float dmd = determinant(md);
    bool jok = abs(dmd) > 1e-24;
    mat2 J = jok ? (mu * inverse(md)) : mat2(0.0);                         // d(uv) / d(disk coordinate)
    vec2 uvt = clamp(vec2(0.5) + v_texcoord0 + J * (dt - dv), vec2(-2.0), vec2(3.0));
    vec2 gx = J * dFdx(dt);
    vec2 gy = J * dFdy(dt);
    float q = length(dt);                                 // 0 = disk center, 1 = limb
    float fw = max(fwidth(q), 1e-4);
    vec4 tex = textureGrad(u_tex0, uvt, gx, gy);
    vec4 nrm = textureGrad(u_tex0_nrm, uvt, gx, gy);
    float qc = min(q, 1.0);
    vec3 tp = (q > 1e-6) ? ((dt.x * e1 + dt.y * e2) / q) : e1;
    float sq = sqrt(max(1.0 - qc * qc, 1e-4));
    vec3 n = qc * tp - sqrt(max(1.0 - qc * qc, 0.0)) * c;                   // sphere normal, faces the camera
    float dj = determinant(J);
    mat2 Ji = (abs(dj) > 1e-24) ? inverse(J) : mat2(1.0);                   // d(disk coordinate) / d(uv)
    vec2 dc = qc * vec2(dot(tp, e1), dot(tp, e2));
    vec3 tt = normalize(Ji[0].x * e1 + Ji[0].y * e2 + (dot(Ji[0], dc) / sq) * c);   // surface direction of +u
    vec3 bb = normalize(Ji[1].x * e1 + Ji[1].y * e2 + (dot(Ji[1], dc) / sq) * c);   // surface direction of +v
    float sd = sign(determinant(mat2(gx, gy)));           // same sign rules as the stock tangent frame
    float sh = sign(dot(cross(tt, bb), n)) * sd;
    vec3 nm = (nrm.xyz * 2.0) - vec3(1.0);
    vec3 nd = normalize(((tt * sh) * nm.x) + ((bb * sh) * nm.y) + (n * sqrt(max(0.0, 1.0 - length(nm.xy)))));
    float mask = 1.0 - smoothstep(1.0 - fw, 1.0 + fw, q);
    // Surface light. Stock: Lambert, mu0 / pi. The real moon is not Lambert: it has no limb darkening
    // and its crescent stays bright up to the limb (dust surface). MOON_LS = 1: Lommel-Seeliger law
    // 2 mu0 / (mu0 + mue) / pi (same value as Lambert at the disk center at full moon). MOON_LS = 0: stock.
    // mu0 = cos(sun angle) with the normal map, mue = cos(view angle) of the sphere.
    float mu0 = max(0.0, dot(nd, s));
    float mue = sqrt(max(1.0 - qc * qc, 0.0));
    float ls = 2.0 * mu0 / max(mu0 + mue, 1e-4);
    float shade = mix(mu0, ls, MOON_LS) * 0.3183098733425140380859375;
    vec3 moon = (jok && mask > 0.0) ? (tex.xyz * L * shade * mask) : vec3(0.0);

    vec3 col = (moon * stock_sky.w) + stock_sky.xyz + glow;
    if (ss > 0.0 && mask <= 0.0)
    {
        discard;                                          // sun up: stock dome sky, moon disk only
    }
    // Alpha = disk mask. X-Plane blends the moon draw premultiplied (ONE, ONE_MINUS_SRC_ALPHA; tested
    // 2026-10-10, probe 2.5). Disk: replace (stock). Outside the disk: the glow adds to the sky and the stars.
    data_out0 = vec4(mix(glow, col, mask), mask);
}
