// A simple Vanilla JS Task Tracker to test framework migration
let tasks = [];
let taskCount = 0;

function addTask() {
    const input = document.getElementById('taskInput');
    const taskText = input.value.trim();
    
    if (taskText !== "") {
        tasks.push(taskText);
        taskCount++;
        updateDisplay();
        input.value = ""; // Clear input
    } else {
        alert("Please enter a task!");
    }
}

function removeTask(index) {
    tasks.splice(index, 1);
    taskCount--;
    updateDisplay();
}

function updateDisplay() {
    const list = document.getElementById('taskList');
    const counter = document.getElementById('counter');
    
    // Update counter text
    counter.innerText = `Total Tasks: ${taskCount}`;
    
    // Rebuild the list in the DOM
    list.innerHTML = "";
    tasks.forEach((task, index) => {
        const li = document.createElement('li');
        li.innerHTML = `
            <span>${task}</span>
            <button onclick="removeTask(${index})">Delete</button>
        `;
        list.appendChild(li);
    });
}

// Initial event listener setup
document.getElementById('addBtn').addEventListener('click', addTask);