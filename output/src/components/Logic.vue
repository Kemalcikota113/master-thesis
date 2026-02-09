<template>
  <div>
    <input id="taskInput" type="text" v-model="taskInputVal">
    <button id="addBtn" @click="addTask">Add Task</button>

    <ul id="taskList">
      <li v-for="(task, index) in tasks" :key="index">
        <span>{{ task }}</span>
        <button @click="removeTask(index)">Delete</button>
      </li>
    </ul>

    <p id="counter">Total Tasks: {{ taskCount }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';

const taskInputVal = ref('');
const tasks = ref<string[]>([]);
const taskCount = computed(() => tasks.value.length);

const addTask = () => {
  if (taskInputVal.value.trim() !== "") {
    tasks.value.push(taskInputVal.value.trim());
    taskInputVal.value = "";
  } else {
    alert("Please enter a task!");
  }
}

const removeTask = (index: number) => {
  tasks.value.splice(index, 1);
}
</script>