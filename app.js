const title = document.getElementById("myTitle");

function handleClick(event){
    location.href = "C:/Users/Administrator/Desktop/Java_Script/Profile-Page/index.html";
}

if (title) {
    title.addEventListener("click", handleClick);
}

let activePublicationTopic = "all";

function getPublicationItems(container) {
    if (!container) {
        return [];
    }

    return Array.from(container.querySelectorAll("ul > li"));
}

function getPublicationTopics(item) {
    return Array.from(item.querySelectorAll("span.label"))
        .map((label) => label.textContent.trim().replace(/\s+/g, " "))
        .filter(Boolean);
}

function annotatePublicationItem(item) {
    item.dataset.publicationTopics = JSON.stringify(getPublicationTopics(item));
}

function itemMatchesPublicationTopic(item, topic) {
    if (topic === "all") {
        return true;
    }

    try {
        return JSON.parse(item.dataset.publicationTopics || "[]").includes(topic);
    } catch (error) {
        return getPublicationTopics(item).includes(topic);
    }
}

function getPublicationYear(item) {
    const text = item.innerText || item.textContent || "";
    const years = text.match(/\b(19|20)\d{2}\b/g);
    return years ? years[0] : "Other";
}

function buildPublicationYearView() {
    const categoryView = document.getElementById("publications-category-view");
    const yearView = document.getElementById("publications-year-view");

    if (!categoryView || !yearView || yearView.dataset.ready === "true") {
        return;
    }

    const preprintHeading = Array.from(categoryView.querySelectorAll("h2")).find((heading) =>
        heading.textContent.toLowerCase().includes("preprint")
    );
    const preprintList = preprintHeading ? preprintHeading.nextElementSibling : null;
    const preprintItems = preprintList && preprintList.tagName === "UL"
        ? Array.from(preprintList.children).filter((child) => child.tagName === "LI")
        : [];
    const items = getPublicationItems(categoryView).filter(
        (item) => !preprintItems.includes(item)
    );
    const groupedItems = new Map();

    if (preprintItems.length > 0) {
        const preprintSection = document.createElement("div");
        preprintSection.className = "publication-year-block";

        const heading = document.createElement("h2");
        heading.textContent = "In submission preprints";
        preprintSection.appendChild(heading);

        const list = document.createElement("ul");
        preprintItems.forEach((item) => {
            const clone = item.cloneNode(true);
            annotatePublicationItem(clone);
            list.appendChild(clone);
        });
        preprintSection.appendChild(list);

        yearView.appendChild(preprintSection);
    }

    items.forEach((item) => {
        const year = getPublicationYear(item);

        if (!groupedItems.has(year)) {
            groupedItems.set(year, []);
        }

        const clone = item.cloneNode(true);
        annotatePublicationItem(clone);
        groupedItems.get(year).push(clone);
    });

    Array.from(groupedItems.keys())
        .sort((a, b) => {
            if (a === "Other") return 1;
            if (b === "Other") return -1;
            return Number(b) - Number(a);
        })
        .forEach((year) => {
            const section = document.createElement("div");
            section.className = "publication-year-block";

            const heading = document.createElement("h2");
            heading.textContent = year;
            section.appendChild(heading);

            const list = document.createElement("ul");
            groupedItems.get(year).forEach((item) => list.appendChild(item));
            section.appendChild(list);

            yearView.appendChild(section);
        });

    yearView.dataset.ready = "true";
}

function getPublicationTopicOrder(topics) {
    const publicationsSection = document.getElementById("publications");
    const summaryOrder = publicationsSection
        ? Array.from(publicationsSection.children)
            .filter((child) => child.matches("span.label"))
            .map((label) => label.textContent.split(":")[0].trim())
            .filter((label) => label && label !== "Total")
        : [];

    return [
        ...summaryOrder.filter((topic) => topics.has(topic)),
        ...Array.from(topics.keys())
            .filter((topic) => !summaryOrder.includes(topic))
            .sort(),
    ];
}

function buildPublicationTopicControls() {
    const categoryView = document.getElementById("publications-category-view");
    const controls = document.getElementById("publication-topic-controls");

    if (!categoryView || !controls || controls.dataset.ready === "true") {
        return;
    }

    const topicCounts = new Map();
    const topicClasses = new Map();
    const items = getPublicationItems(categoryView);

    items.forEach((item) => {
        annotatePublicationItem(item);

        Array.from(item.querySelectorAll("span.label")).forEach((label) => {
            const topic = label.textContent.trim().replace(/\s+/g, " ");
            const labelClass = Array.from(label.classList).find((className) =>
                className.startsWith("label-") && className !== "label"
            );

            if (topic && labelClass && !topicClasses.has(topic)) {
                topicClasses.set(topic, labelClass);
            }
        });

        new Set(getPublicationTopics(item)).forEach((topic) => {
            topicCounts.set(topic, (topicCounts.get(topic) || 0) + 1);
        });
    });

    const allButton = createPublicationTopicButton("all", `All Topics (${items.length})`, "label-total");
    allButton.classList.add("active");
    allButton.setAttribute("aria-pressed", "true");
    controls.appendChild(allButton);

    getPublicationTopicOrder(topicCounts).forEach((topic) => {
        controls.appendChild(
            createPublicationTopicButton(topic, `${topic} (${topicCounts.get(topic)})`, topicClasses.get(topic))
        );
    });

    controls.dataset.ready = "true";
}

function createPublicationTopicButton(topic, label, colorClass) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "publication-topic-toggle";

    if (colorClass) {
        button.classList.add(colorClass);
    }

    button.dataset.publicationTopic = topic;
    button.textContent = label;
    button.setAttribute("aria-pressed", "false");
    button.addEventListener("click", () => {
        setPublicationTopic(topic);
    });

    return button;
}

function setPublicationTopic(topic) {
    activePublicationTopic = topic;

    document.querySelectorAll(".publication-topic-toggle").forEach((button) => {
        const isActive = button.dataset.publicationTopic === topic;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
    });

    applyPublicationTopicFilter();
}

function updatePublicationSectionVisibility() {
    const categoryView = document.getElementById("publications-category-view");
    const yearView = document.getElementById("publications-year-view");

    if (categoryView) {
        categoryView.querySelectorAll("h2").forEach((heading) => {
            const blocks = [];
            let block = heading.nextElementSibling;

            while (block && block.tagName !== "H2") {
                blocks.push(block);
                block = block.nextElementSibling;
            }

            const hasVisibleItem = blocks.some((sectionBlock) =>
                Array.from(sectionBlock.querySelectorAll("ul > li")).some(
                    (item) => !item.classList.contains("publication-item-hidden")
                )
            ) || blocks.some(
                (item) => !item.classList.contains("publication-item-hidden")
                    && item.matches("li")
            );

            heading.classList.toggle("publication-empty-section", !hasVisibleItem);
            blocks.forEach((sectionBlock) => {
                sectionBlock.classList.toggle("publication-empty-section", !hasVisibleItem);
            });
        });
    }

    if (yearView) {
        yearView.querySelectorAll(".publication-year-block").forEach((block) => {
            const hasVisibleItem = Array.from(block.querySelectorAll("ul > li")).some(
                (item) => !item.classList.contains("publication-item-hidden")
            );
            block.classList.toggle("publication-empty-section", !hasVisibleItem);
        });
    }
}

function applyPublicationTopicFilter() {
    document.querySelectorAll(".publication-view ul > li").forEach((item) => {
        item.classList.toggle(
            "publication-item-hidden",
            !itemMatchesPublicationTopic(item, activePublicationTopic)
        );
    });

    updatePublicationSectionVisibility();
}

function showPublicationView(viewName) {
    const categoryView = document.getElementById("publications-category-view");
    const yearView = document.getElementById("publications-year-view");
    const buttons = document.querySelectorAll(".publication-toggle");

    if (!categoryView || !yearView) {
        return;
    }

    if (viewName === "year") {
        buildPublicationYearView();
    }

    categoryView.classList.toggle("publication-view-hidden", viewName !== "category");
    yearView.classList.toggle("publication-view-hidden", viewName !== "year");

    buttons.forEach((button) => {
        const isActive = button.dataset.publicationView === viewName;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
    });

    applyPublicationTopicFilter();
}

buildPublicationTopicControls();

document.querySelectorAll(".publication-toggle").forEach((button) => {
    button.addEventListener("click", () => {
        showPublicationView(button.dataset.publicationView);
    });
});
