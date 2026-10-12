// =====================================================================================
// moon_vertex.glsl - Moon sky mod, vertex stages (astronomical stages 0 and 2).
//
// Urania (engine/shaders.py) keeps the stock declarations of the stage (inputs, outputs, uniform
// blocks) and replaces only the main function. It adds the settings (@SETTINGS@) and
// the alias MXFORM (transform block). Stage 2 also gets MIMM (point size block).
//
// The stock moon mesh is a hemisphere that faces the camera. This stage moves each vertex
// to a sky point: sky angle from the moon = 2 x (vertex normal angle from the view line).
// The hemisphere rim goes to 180 deg. Thus the moon draw covers the whole sky.
// The fragment stage paints the moonlit sky glow and draws the moon disk again.
// X-Plane does not fill modelview_inverse for this draw: the stage computes its own inverse.
// =====================================================================================

// @SETTINGS@

void main()
{
    int inst = gl_InstanceIndex - gl_BaseInstance;
    gl_ViewportIndex = inst % MXFORM.u_viewport_count;
    gl_Layer = (inst % MXFORM.u_layer_count) + MXFORM.u_layer_offset;
    int i = inst % MXFORM.u_transform_count;
    mat4 mv = MXFORM.modelview_matrix[i];
    vec4 src = vec4(a_vertex - MXFORM.u_mv_offset, 1.0);
    vec3 pe = (mv * src).xyz;
    vec3 ne = normalize(mat3(mv[0].xyz, mv[1].xyz, mv[2].xyz) * a_normal);
    float dist = length(pe);
    vec3 c = normalize(pe - (MOON_SIN_R * dist) * ne);  // moon center direction
    float cn = dot(ne, c);
    vec3 d3 = ne - cn * c;                              // normal part across the moon line (disk coordinate)
    float sl = length(d3);
    vec3 tu = (sl > 1e-6) ? (d3 / sl) : vec3(0.0);
    float al = min(2.0 * acos(clamp(-cn, -1.0, 1.0)), 3.14159265);   // sky angle from the moon
    vec3 pn = (cos(al) * c + sin(al) * tu) * dist;      // sky point, same distance as the moon
    vec4 pm = inverse(mv) * vec4(pn, 1.0);
    vec4 pos = MXFORM.mvp_matrix[i] * vec4(pm.xyz / pm.w, 1.0);
    if (any(isnan(pos)) || any(isinf(pos)))
    {
        pos = MXFORM.mvp_matrix[i] * src;               // stock position: glow only on the moon disk
        pn = pe;
    }
    gl_Position = pos;
    v_eye = i;
    mat4 pj = MXFORM.mvp_matrix[i] * inverse(mv);       // projection matrix
    // Square 90 deg projection = cube face = the sky render for scene light (tested 2026-10-10).
    float sq90 = (abs(abs(pj[0][0]) - 1.0) < 0.02 && abs(abs(pj[1][1]) - 1.0) < 0.02) ? 1.0 : 0.0;
    float multi = ((MXFORM.u_layer_count > 1) ? 1.0 : 0.0) + ((MXFORM.u_transform_count > 1) ? 2.0 : 0.0);
    v_ratio = vec2(sq90, multi);                        // pass flags (the stock fragment use of v_ratio is replaced)
    v_dir_wrl = d3;
    v_normal_eye = c;
    v_position_eye = pn;
    v_texcoord0 = a_texcoord0 - vec2(0.5);              // UV relative to the texture center: precise derivatives
    // @POINT_SIZE@
}
