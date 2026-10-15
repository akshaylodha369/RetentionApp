/* RetentionApp Motion System: progressive enhancements only */
(() => {
  const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) return;
  const selector = ".discover-intro,.location-note,.search-box,.filters,.results-panel,.business-card,.offer-card,.profile-card,.owner-card,.business-card-owner,.auth-panel,.auth-story,.auth-perk,.dashboard-header,.business-profile,.profile-page,.closing-note,.business-section,.offer-box";
  const elements = [...document.querySelectorAll(selector)];
  if ("IntersectionObserver" in window && elements.length) {
    document.body.classList.add("ra-motion-ready");
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("ra-visible");
      observer.unobserve(entry.target);
    }), {threshold:0.08, rootMargin:"0px 0px -28px 0px"});
    elements.forEach((el,i) => {
      el.classList.add("ra-reveal","ra-stagger-"+((i%5)+1));
      if(el.getBoundingClientRect().top < window.innerHeight*.92) requestAnimationFrame(()=>el.classList.add("ra-visible"));
      else observer.observe(el);
    });
  }
  if (window.matchMedia && window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    document.querySelectorAll(".business-card,.offer-card,.profile-card,.owner-card").forEach(card => {
      card.classList.add("ra-tilt");
      card.addEventListener("pointermove", e => {
        const r=card.getBoundingClientRect(), x=(e.clientX-r.left)/r.width, y=(e.clientY-r.top)/r.height;
        card.style.transform="perspective(900px) translateY(-4px) rotateX("+((.5-y)*3).toFixed(2)+"deg) rotateY("+((x-.5)*3).toFixed(2)+"deg)";
      });
      card.addEventListener("pointerleave",()=>{card.style.transform="";});
    });
  }
})();
