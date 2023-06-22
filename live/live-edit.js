(function () {
  const ws = new WebSocket(`ws://localhost:${ws_port}`);

  let
    editButton,
    editSource,
    saveButton,
    cancelButton,
    controls,
    infoModal,
    errorMessageDialog;

  ws.onmessage = function (e) {
    let data = JSON.parse(e.data);
    switch (data.action) {
      case 'get_contents': onPageContentsReceived(data); break;
      case 'set_contents': onSavePageContentsReceived(data); break;
      case 'rename_file': onRenamePageReceived(data); break;
      case 'delete_file': onDeletePageReceived(data); break;
    }
  }

  const showError = function (message) {
    errorMessageDialog.textContent = message;
    errorMessageDialog.showModal();
  }

  const showInfo = function (message) {
    infoModal.textContent = message;
    infoModal.showModal();
  }

  const enterEditMode = function () {
    editButton.classList.add('live-edit-hidden');
    editSource.classList.remove('live-edit-hidden');
    saveButton.classList.remove('live-edit-hidden');
    cancelButton.classList.remove('live-edit-hidden');
  }

  const exitEditMode = function () {
    editButton.classList.remove('live-edit-hidden');
    editSource.classList.add('live-edit-hidden');
    saveButton.classList.add('live-edit-hidden');
    cancelButton.classList.add('live-edit-hidden');
  }

  const onDeletePageReceived = function (data) {
    if (data.success) {
      showInfo(`Page deleted, waiting on a refresh to 404 from MkDocs...`);
    } else {
      showError(data.error);
    }
  }

  const onRenamePageReceived = function (data) {
    if (data.success) {
      page_path = data.new_path;
      editButton.disabled = false;
      showInfo(`Waiting on a MkDocs redirect to ${data.new_url}...`);
    } else {
      showError(data.error);
    }
  }

  const onSavePageContents = function () {
    saveButton.disabled = true;
    cancelButton.classList.add('live-edit-hidden');
    ws.send(JSON.stringify({
      'action': 'set_contents',
      'path': page_path,
      'contents': editSource.value,
    }));
  }

  const onSavePageContentsReceived = function (data) {
    saveButton.disabled = false;
    if (data.success) {
      editSource.classList.add('live-edit-hidden');
      saveButton.classList.add('live-edit-hidden');
      editButton.classList.remove('live-edit-hidden');
      showInfo('Page saved, waiting on a refresh from MkDocs...');
    } else {
      showError(data.error);
    }
  }

  const onPageContentsReceived = function (data) {
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
    // add the textbox to the controls
    controls.appendChild(editSource);
    // add the save button after the textbox
    editSource.parentNode.insertBefore(saveButton, editSource.nextSibling);
    // add the cancel button after the save button
    saveButton.parentNode.insertBefore(cancelButton, saveButton.nextSibling);
    enterEditMode();
  }

  const editPage = function () {
    editButton.disabled = true;
    ws.send(JSON.stringify({
      'action': 'get_contents',
      'path': page_path,
    }));
  }

  const renamePage = function () {
    let new_path = prompt(
      'Enter a new path for this page',
      page_path,
    );
    if (new_path === page_path) {
      return showError('The new path cannot be the same as the current path');
    }
    if (new_path) {
      ws.send(JSON.stringify({
        'action': 'rename_file',
        'path': page_path,
        'new_path': new_path,
      }));
    } else {
      return showError('The new path cannot be empty');
    }
  }

  const addEditButton = function () {
    // add a button
    editButton = document.createElement('button');
    editButton.innerHTML = '✏️ Edit';
    editButton.className = 'live-edit-button';
    editButton.title = 'Edit the contents of this page';
    editButton.addEventListener('click', editPage);
    controls.appendChild(editButton);
  }

  const addRenameButton = function () {
    // add a button
    renameButton = document.createElement('button');
    renameButton.innerHTML = '📝 Rename';
    renameButton.className = 'live-edit-button';
    renameButton.title = 'Change the filename of this page';
    renameButton.addEventListener('click', renamePage);
    controls.appendChild(renameButton);
  }

  const addDeleteButton = function () {
    // add a button
    deleteButton = document.createElement('button');
    deleteButton.innerHTML = '🗑️ Delete';
    deleteButton.className = 'live-edit-button';
    deleteButton.title = 'Delete this page';
    deleteButton.addEventListener('click', function () {
      if (confirm('Are you sure you want to delete this page?')) {
        ws.send(JSON.stringify({
          'action': 'delete_file',
          'path': page_path,
        }));
      }
    });
    controls.appendChild(deleteButton);
  }

  const addInfoModal = function () {
    infoModal = document.createElement('dialog');
    infoModal.open = false;
    infoModal.classList.add('live-edit-modal');
    infoModal.classList.add('live-edit-info-modal');
    infoModal.addEventListener('click', function () {
      infoModal.close();
    });
    document.body.appendChild(infoModal);
  }

  const addErrorMessageDialog = function () {
    errorMessageDialog = document.createElement('dialog');
    errorMessageDialog.open = false;
    errorMessageDialog.classList.add('live-edit-modal');
    errorMessageDialog.classList.add('live-edit-error-message-dialog');
    errorMessageDialog.addEventListener('click', function () {
      errorMessageDialog.close();
    });
    document.body.appendChild(errorMessageDialog);
  }

  const initialize = function () {
    controls = document.createElement('div');
    controls.className = 'live-edit-controls';
    // add a label to the controls
    label = document.createElement('span');
    label.innerHTML = 'Live Edit:';
    label.className = 'live-edit-label';
    controls.appendChild(label);
    // add the controls to the page after the H1
    let article = document.querySelector('article');
    if (article) {
      article.prepend(controls);
      addEditButton();
      addRenameButton();
      addDeleteButton();
      addInfoModal();
      addErrorMessageDialog();
    }
  };

  document.addEventListener('DOMContentLoaded', initialize);
})();
