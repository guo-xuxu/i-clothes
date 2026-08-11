const MAX_FILES = 3;

const uploadArea = document.getElementById("upload-area");
const fileInput = document.getElementById("file-input");
const preview = document.getElementById("preview");
const form = document.getElementById("recommend-form");
const descriptionEl = document.getElementById("description");
const submitBtn = document.getElementById("submit-btn");
const result = document.getElementById("result");
const resultContent = document.getElementById("result-content");

let selectedFiles = [];

uploadArea.addEventListener("click", () => fileInput.click());

uploadArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadArea.classList.add("dragover");
});

uploadArea.addEventListener("dragleave", () => {
    uploadArea.classList.remove("dragover");
});

uploadArea.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadArea.classList.remove("dragover");
    handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener("change", () => handleFiles(fileInput.files));

function handleFiles(fileList) {
    const files = Array.from(fileList).filter((f) =>
        ["image/jpeg", "image/png"].includes(f.type)
    );
    selectedFiles = files.slice(0, MAX_FILES);
    renderPreview();
}

function renderPreview() {
    preview.innerHTML = "";
    selectedFiles.forEach((file) => {
        const img = document.createElement("img");
        img.src = URL.createObjectURL(file);
        preview.appendChild(img);
    });
}

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    if (selectedFiles.length === 0) {
        alert("请至少上传一张照片");
        return;
    }

    const formData = new FormData();
    selectedFiles.forEach((file) => formData.append("images", file));
    formData.append("description", descriptionEl.value);

    submitBtn.disabled = true;
    submitBtn.textContent = "生成中…";
    result.hidden = true;

    try {
        const resp = await fetch("/api/recommend", {
            method: "POST",
            body: formData,
        });
        const data = await resp.json();

        if (!resp.ok) {
            throw new Error(data.detail || "请求失败");
        }

        resultContent.textContent = data.suggestion;
        result.hidden = false;
    } catch (err) {
        resultContent.textContent = `出错了：${err.message}`;
        result.hidden = false;
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "生成穿搭建议";
    }
});
