
document.addEventListener("DOMContentLoaded", () => { loadSummary () });
function loadSummary () {
    fetch('/api/chapters')
        .then(res => res.json())
        .then(chapters => {
            const navContainer = document.getElementById('homeChaptersList');
            navContainer.innerHTML = ""
            document.getElementById('welcomeJumbotron').style.display = "none";
            document.getElementById('sh').style.display = "none";
            const target = document.getElementById('versesFeedTarget');
            while (target.children.length > 1) {
              target.removeChild(target.lastChild);
            }
            chapters.forEach((ch, idx) => {
                // Inject left menu bar item configurations sequentially
                const navBtn = document.createElement('button');
                navBtn.className = "list-group-item list-group-item-action fw-bold d-flex justify-content-between align-items-center py-3";
                navBtn.innerHTML = `<span>Chapter ${ch.chapter_number}</span> <span class="badge bg-warning text-dark rounded-pill">${ch.verse_count} Verses</span>`;
                navBtn.onclick = () => renderChapterFeed(ch.chapter_number);
                navContainer.appendChild(navBtn);
                // Inject Right menu bar Summary sequentially
                const block = document.createElement('div');
                block.className = "card shadow-sm border-0 mb-4 border-start border-4 border-warning";
                block.innerHTML = `
                    <div class="card-body p-4">
                        <h5 class="text-primary mb-2">Chapter ${ch.chapter_number} - ${ch.name} </h5>
                        <p class="text-muted fs-6 mb-3"><strong>Summary:</strong> ${ch.summary}</p>
                    </div>
                `;
                target.appendChild(block);
                document.getElementById("canvasDismiss").click();
            });
        });
}

function renderChapterFeed(chapterNum) {
    const chapter = "chapter";
    const url = `/api/chapterShlokas?${chapter}=${chapterNum}`;
    fetch(url)
        .then(res => res.json())
        .then(data => {
            document.getElementById('welcomeJumbotron').style.display = "none";
            const target = document.getElementById('versesFeedTarget');
            while (target.children.length > 1) {
                target.removeChild(target.lastChild);
            }
            const header = document.createElement('h3');
                header.className = "text-dark border-bottom pb-2 mb-4 ";
                header.innerHTML = `<i class="fa-solid fa-book text-primary text-center me-2">Chapter-${data[0].chapter_number}: ${data[0].name}</i>`;
                target.appendChild(header);
            // target.innerHTML = `<!--<h3 class="text-dark border-bottom pb-2 mb-4"><i class="fa-solid fa-book text-warning me-2"></i> Chapter - ${data[0].chapter_number} : ${data[0].name} </h3>-->`;

            data.forEach(v => {
                const block = document.createElement('div');
                block.className = "card shadow-sm border-0 mb-4 border-start border-4 border-warning";
                block.innerHTML = `
                <div class="card-body p-4">
                    <h5 class="text-primary mb-2">Verse ${v.chapter_number}.${v.verse_number}</h5>
                    <p class="fs-4 fw-bold text-dark font-monospace mb-3" style="line-height:1.6; white-space: pre-line;"> ${v.shloka}</p>
                    <p class="text-muted fs-6 mb-3"><strong>Translation:</strong> ${v.meaning.en.description}</p>
                </div>
            `;
                target.appendChild(block);
                document.getElementById("canvasDismiss").click();
            });
        }).catch(err => console.error("Fetch request failed:", err));
}
