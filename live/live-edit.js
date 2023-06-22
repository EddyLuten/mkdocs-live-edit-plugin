const ws = new WebSocket('ws://localhost:8484');

let editButton;
let editSource;
let saveButton;
let cancelButton;
let controls;

ws.onmessage = function(e) {
    let data = JSON.parse(e.data);
    switch (data.action) {
        case 'get_contents':
            onPageContentsReceived(data);
            break;
        case 'set_contents':
            onSavePageContentsReceived(data);
            break;
    }
}

const enterEditMode = function() {
    editButton.classList.add('live-edit-hidden');
    editSource.classList.remove('live-edit-hidden');
    saveButton.classList.remove('live-edit-hidden');
    cancelButton.classList.remove('live-edit-hidden');
}

const exitEditMode = function() {
    editButton.classList.remove('live-edit-hidden');
    editSource.classList.add('live-edit-hidden');
    saveButton.classList.add('live-edit-hidden');
    cancelButton.classList.add('live-edit-hidden');
}

const onSavePageContents = function() {
    saveButton.disabled = true;
    cancelButton.classList.add('live-edit-hidden');
    ws.send(JSON.stringify({
        'action':   'set_contents',
        'path':     page_path,
        'contents': editSource.value,
    }));
}

const onSavePageContentsReceived = function(data) {
    saveButton.disabled = false;
    if (data.success) {
        editSource.classList.add('live-edit-hidden');
        saveButton.classList.add('live-edit-hidden');
        editButton.classList.remove('live-edit-hidden');
    }
}

const onPageContentsReceived = function(data) {
    editButton.disabled = false;
    editButton.classList.add('live-edit-hidden');
    if (editSource) {
        enterEditMode();
        return;
    }

    // add a textbox to the page
    editSource = document.createElement('textarea');
    editSource.innerHTML = data.contents;
    editSource.className = 'live-edit-source';
    // add a save button
    saveButton = document.createElement('button');
    saveButton.innerHTML = 'Save';
    saveButton.classList.add('live-edit-button');
    saveButton.classList.add('live-edit-save-button');
    saveButton.addEventListener('click', onSavePageContents);
    // add a cancel button
    cancelButton = document.createElement('button');
    cancelButton.innerHTML = 'Cancel';
    cancelButton.classList.add('live-edit-button');
    cancelButton.classList.add('live-edit-cancel-button');
    cancelButton.addEventListener('click', exitEditMode);
    // find the first H1
    let h1 = document.querySelector('h1');
    if (h1) {
        // add the textbox before the H1
        h1.parentNode.insertBefore(editSource, h1);
        // add the save button after the textbox
        editSource.parentNode.insertBefore(saveButton, editSource.nextSibling);
        // add the cancel button after the save button
        saveButton.parentNode.insertBefore(cancelButton, saveButton.nextSibling);
    }
    enterEditMode();
}

const editPage = function() {
    editButton.disabled = true;
    ws.send(JSON.stringify({
        'action': 'get_contents',
        'path': page_path,
    }));
}

const addEditButton = function() {
    // find the first H1
    let h1 = document.querySelector('h1');
    if (h1) {
        // add a button
        editButton = document.createElement('button');
        editButton.innerHTML = '✏️';
        editButton.className = 'live-edit-button';
        editButton.addEventListener('click', editPage);
        // add the button inside the H1
        h1.prepend(editButton);
    }
}

document.addEventListener('DOMContentLoaded', function() {
    addEditButton();
});
