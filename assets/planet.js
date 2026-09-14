// Orthographic sphere and ring intersections. All colors are composited
    // back to front; the planet is opaque even on its unlit hemisphere.
    (() => {
      const canvas = document.getElementById('planet');
      const ctx = canvas.getContext('2d');
      const size = canvas.width;
      const image = ctx.createImageData(size, size);
      const data = image.data;
      const light = [-0.58, 0.57, 0.582];
      const normal = [0.337, 0.834, 0.437];
      const dot = (a, b) => a[0]*b[0] + a[1]*b[1] + a[2]*b[2];
      const mix = (a, b, t) => a.map((v, i) => v*(1-t)+b[i]*t);
      const smooth = (a,b,x) => { const t=Math.max(0,Math.min(1,(x-a)/(b-a))); return t*t*(3-2*t); };
      function ringAt(x,y,z) {
        const r = Math.hypot(x,y,z);
        if (r<1.28 || r>2.16) return null;
        const edge = smooth(1.28,1.32,r)*(1-smooth(2.12,2.16,r));
        const gap = 1-.94*smooth(1.74,1.754,r)*(1-smooth(1.793,1.81,r));
        const bands = .56+.17*Math.sin(r*210)+.10*Math.sin(r*487)+.08*Math.sin(r*91);
        const warmth = .5+.5*Math.sin(r*10);
        let color = mix([146,144,206],[231,194,157],warmth);
        const toward = x*light[0]+y*light[1]+z*light[2];
        // A ray from a ring particle toward the light may intersect the globe.
        const blocked = toward<0 && r*r-toward*toward<1;
        color=color.map(v=>v*(blocked?.13:.91));
        return { color, alpha: edge*gap*bands*.80 };
      }
      for(let py=0;py<size;py++) for(let px=0;px<size;px++) {
        const x=(px+.5-size/2)*4.8/size;
        const y=(size/2-py-.5)*4.8/size;
        const radius2=x*x+y*y;
        const rz=-(normal[0]*x+normal[1]*y)/normal[2];
        const ring=ringAt(x,y,rz);
        let color=[0,0,0], alpha=0;
        const blend=(c,a)=> {
          const next=a+alpha*(1-a);
          color=color.map((v,i)=>(c[i]*a+v*alpha*(1-a))/(next||1));
          alpha=next;
        };
        if(ring) blend(ring.color,ring.alpha);
        if(radius2<=1) {
          const z=Math.sqrt(1-radius2);
          const p=[x,y,z];
          const lat=dot(normal,p);
          const swirl=.024*Math.sin(x*19+z*11)+.015*Math.sin(z*33-y*17)+.008*Math.sin(x*67+y*31);
          const band=.5+.5*Math.sin((lat+swirl)*39);
          const detail=.5+.5*Math.sin((lat+swirl*.7)*132);
          let surface=mix([62,66,134],[142,133,192],band*.78+detail*.12);
          const storm=Math.exp(-((x+.25)**2*50+(lat-.14)**2*240));
          surface=mix(surface,[184,162,181],storm*.55);
          let illumination=Math.max(0,dot(p,light));
          // Project the planet's point toward the light onto the ring plane.
          const t=-lat/dot(normal,light);
          if(t>0 && illumination>0) {
            const cast=ringAt(x+light[0]*t,y+light[1]*t,z+light[2]*t);
            if(cast) illumination*=1-cast.alpha*.82;
          }
          const rim=Math.pow(1-z,3)*Math.max(0,dot(p,light))*.27;
          color=surface.map((v,i)=>v*(.055+.96*illumination)+[90,100,185][i]*rim);
          alpha=1;
          // Only the ring intersection in front of the sphere can show here.
          if(ring && rz>z) blend(ring.color,ring.alpha);
        } else if(radius2<1.085) {
          const r=Math.sqrt(radius2);
          const lit=Math.max(0,(x*light[0]+y*light[1])/r);
          const haze=Math.exp(-(r-1)*110)*lit*.46;
          blend([133,145,233],haze);
        }
        const i=(py*size+px)*4;
        data[i]=color[0]; data[i+1]=color[1]; data[i+2]=color[2]; data[i+3]=alpha*255;
      }
      ctx.putImageData(image,0,0);
    })();
