// Add your profile links here. A link left empty simply doesn't appear on the site.
const SOCIAL = {
  github: "https://github.com/gokuldas439",
  linkedin: "",
  instagram: "",
};

const ICONS = {
  github: '<path d="M12 .5a11.5 11.5 0 0 0-3.64 22.41c.58.1.79-.25.79-.56v-2c-3.2.7-3.88-1.37-3.88-1.37-.53-1.33-1.29-1.69-1.29-1.69-1.05-.72.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.71 1.26 3.37.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.19-3.09-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.17 1.18a11 11 0 0 1 5.77 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.8 1.19 1.83 1.19 3.09 0 4.42-2.69 5.39-5.25 5.68.41.36.78 1.06.78 2.14v3.17c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .5Z"/>',
  linkedin: '<path d="M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5ZM3 9.75h4V21H3V9.75Zm6.5 0h3.83v1.54h.05c.53-1 1.84-2.06 3.78-2.06 4.04 0 4.79 2.66 4.79 6.12V21h-4v-4.95c0-1.18-.02-2.7-1.65-2.7-1.65 0-1.9 1.29-1.9 2.62V21h-4V9.75Z"/>',
  instagram: '<path d="M12 2.2c3.2 0 3.58.01 4.85.07 1.17.05 1.8.25 2.22.41.56.22.96.48 1.38.9.42.42.68.82.9 1.38.16.42.36 1.05.41 2.22.06 1.27.07 1.65.07 4.85s-.01 3.58-.07 4.85c-.05 1.17-.25 1.8-.41 2.22a3.7 3.7 0 0 1-.9 1.38c-.42.42-.82.68-1.38.9-.42.16-1.05.36-2.22.41-1.27.06-1.65.07-4.85.07s-3.58-.01-4.85-.07c-1.17-.05-1.8-.25-2.22-.41a3.7 3.7 0 0 1-1.38-.9 3.7 3.7 0 0 1-.9-1.38c-.16-.42-.36-1.05-.41-2.22C2.21 15.58 2.2 15.2 2.2 12s.01-3.58.07-4.85c.05-1.17.25-1.8.41-2.22.22-.56.48-.96.9-1.38.42-.42.82-.68 1.38-.9.42-.16 1.05-.36 2.22-.41C8.42 2.21 8.8 2.2 12 2.2Zm0 4.77a5.03 5.03 0 1 0 0 10.06 5.03 5.03 0 0 0 0-10.06Zm0 8.3a3.27 3.27 0 1 1 0-6.54 3.27 3.27 0 0 1 0 6.54Zm6.4-8.5a1.18 1.18 0 1 1-2.36 0 1.18 1.18 0 0 1 2.36 0Z"/>',
};

document.querySelectorAll(".social").forEach((holder) => {
  Object.entries(SOCIAL).forEach(([name, url]) => {
    if (!url) return;
    const link = document.createElement("a");
    link.className = "glass";
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener";
    link.setAttribute("aria-label", name);
    link.innerHTML = `<svg viewBox="0 0 24 24">${ICONS[name]}</svg>`;
    holder.append(link);
  });
});

// The animated demo tells this page how tall it needs to be.
window.addEventListener("message", (event) => {
  const frame = document.getElementById("demo");
  if (frame && event.source === frame.contentWindow && event.data && event.data.demoHeight) {
    frame.style.height = `${event.data.demoHeight}px`;
  }
});
