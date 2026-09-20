// Orthographic sphere and ring intersections, drawn per frame on the GPU.
// The surface turns once every 150 seconds around the planet's tilted axis;
// rings, lighting, ring shadow and haze stay fixed to the light. Colors are
// composited back to front and the planet is opaque on its unlit hemisphere.
(() => {
  const canvas = document.getElementById("planet");
  const params = new URLSearchParams(location.search);
  const t = params.get("t");
  const frozen = t !== null && t.trim() !== "" && Number.isFinite(Number(t)) && Number(t) >= 0;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const ROTATION_PERIOD = 150;

  const VERTEX = `attribute vec2 a; void main() { gl_Position = vec4(a, 0.0, 1.0); }`;
  const FRAGMENT = `
    precision highp float;
    uniform float u_time;
    uniform float u_size;
    const vec3 light = vec3(-0.58, 0.57, 0.582);
    const vec3 axis = vec3(0.337, 0.834, 0.437);
    const float TAU = 6.283185307179586;

    // rgb in 0..255 plus coverage; coverage 0 means no ring at this point.
    vec4 ringAt(vec3 q) {
      float r = length(q);
      if (r < 1.28 || r > 2.16) return vec4(0.0);
      float edge = smoothstep(1.28, 1.32, r) * (1.0 - smoothstep(2.12, 2.16, r));
      float gap = 1.0 - 0.94 * smoothstep(1.74, 1.754, r) * (1.0 - smoothstep(1.793, 1.81, r));
      float bands = 0.56 + 0.17 * sin(r * 210.0) + 0.10 * sin(r * 487.0) + 0.08 * sin(r * 91.0);
      float warmth = 0.5 + 0.5 * sin(r * 10.0);
      vec3 color = mix(vec3(146.0, 144.0, 206.0), vec3(231.0, 194.0, 157.0), warmth);
      float toward = dot(q, light);
      // A ray from a ring particle toward the light may intersect the globe.
      bool blocked = toward < 0.0 && r * r - toward * toward < 1.0;
      color *= blocked ? 0.13 : 0.91;
      return vec4(color, edge * gap * bands * 0.80);
    }

    void blend(inout vec3 color, inout float alpha, vec3 c, float a) {
      float next = a + alpha * (1.0 - a);
      color = (c * a + color * alpha * (1.0 - a)) / max(next, 1e-6);
      alpha = next;
    }

    vec3 spin(vec3 p, float angle) {
      float c = cos(angle), s = sin(angle);
      return p * c + cross(axis, p) * s + axis * dot(axis, p) * (1.0 - c);
    }

    void main() {
      float x = (gl_FragCoord.x - u_size / 2.0) * 4.8 / u_size;
      float y = (gl_FragCoord.y - u_size / 2.0) * 4.8 / u_size;
      float radius2 = x * x + y * y;
      float rz = -(axis.x * x + axis.y * y) / axis.z;
      vec4 ring = ringAt(vec3(x, y, rz));
      vec3 color = vec3(0.0);
      float alpha = 0.0;
      if (ring.a > 0.0) blend(color, alpha, ring.rgb, ring.a);
      if (radius2 <= 1.0) {
        float z = sqrt(1.0 - radius2);
        vec3 p = vec3(x, y, z);
        float lat = dot(axis, p);
        // Surface features live in the rotating frame; latitude does not move.
        vec3 q = spin(p, u_time * TAU / ${ROTATION_PERIOD}.0);
        float swirl = 0.024 * sin(q.x * 19.0 + q.z * 11.0) + 0.015 * sin(q.z * 33.0 - q.y * 17.0) + 0.008 * sin(q.x * 67.0 + q.y * 31.0);
        float band = 0.5 + 0.5 * sin((lat + swirl) * 39.0);
        float detail = 0.5 + 0.5 * sin((lat + swirl * 0.7) * 132.0);
        vec3 surface = mix(vec3(62.0, 66.0, 134.0), vec3(142.0, 133.0, 192.0), band * 0.78 + detail * 0.12);
        // One storm, baked on the hemisphere that faced the viewer at t=0.
        float storm = exp(-((q.x + 0.25) * (q.x + 0.25) * 50.0 + (lat - 0.14) * (lat - 0.14) * 240.0)) * smoothstep(0.0, 0.4, q.z);
        surface = mix(surface, vec3(184.0, 162.0, 181.0), storm * 0.55);
        float illumination = max(0.0, dot(p, light));
        // Project the planet's point toward the light onto the ring plane.
        float toPlane = -lat / dot(axis, light);
        if (toPlane > 0.0 && illumination > 0.0) {
          vec4 shadow = ringAt(p + light * toPlane);
          if (shadow.a > 0.0) illumination *= 1.0 - shadow.a * 0.82;
        }
        float rim = pow(1.0 - z, 3.0) * max(0.0, dot(p, light)) * 0.27;
        color = surface * (0.055 + 0.96 * illumination) + vec3(90.0, 100.0, 185.0) * rim;
        alpha = 1.0;
        // Only the ring intersection in front of the sphere can show here.
        if (ring.a > 0.0 && rz > z) blend(color, alpha, ring.rgb, ring.a);
      } else if (radius2 < 1.085) {
        float r = sqrt(radius2);
        float lit = max(0.0, (x * light.x + y * light.y) / r);
        float haze = exp(-(r - 1.0) * 110.0) * lit * 0.46;
        blend(color, alpha, vec3(133.0, 145.0, 233.0), haze);
      }
      gl_FragColor = vec4(color / 255.0, alpha);
    }`;

  // Straight alpha matches the transparent page compositing; the buffer is
  // preserved so the canvas can be inspected and copied after a frame.
  const gl = canvas.getContext("webgl", {
    alpha: true, premultipliedAlpha: false, preserveDrawingBuffer: true, antialias: false,
  });
  if (!gl) { canvas.dataset.renderer = "unavailable"; return; }

  function compile(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error("planet shader: " + gl.getShaderInfoLog(shader));
    }
    return shader;
  }
  const program = gl.createProgram();
  gl.attachShader(program, compile(gl.VERTEX_SHADER, VERTEX));
  gl.attachShader(program, compile(gl.FRAGMENT_SHADER, FRAGMENT));
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error("planet program: " + gl.getProgramInfoLog(program));
  }
  gl.useProgram(program);
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const position = gl.getAttribLocation(program, "a");
  gl.enableVertexAttribArray(position);
  gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
  gl.viewport(0, 0, canvas.width, canvas.height);
  gl.uniform1f(gl.getUniformLocation(program, "u_size"), canvas.width);
  const uTime = gl.getUniformLocation(program, "u_time");

  function draw(seconds) {
    gl.uniform1f(uTime, seconds);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }

  const started = performance.now();
  let pending = 0;
  function frame(now) {
    pending = 0;
    if (frozen || reduced.matches) return;
    draw((now - started) / 1000);
    pending = requestAnimationFrame(frame);
  }
  function syncMotion() {
    if (frozen) { draw(Number(t)); return; }
    if (reduced.matches) { draw(0); return; }
    if (!pending) pending = requestAnimationFrame(frame);
  }
  reduced.addEventListener("change", syncMotion);
  canvas.dataset.renderer = "webgl";
  syncMotion();
})();
