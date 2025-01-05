<script setup>
import { ref } from 'vue'
const totalStudy = ref(0)
const totalAuthor = ref(0)
const studyCheckboxes = ref([])
const authorCheckboxes = ref([])
const downloadLink = ref('')
const fileInput = ref(null)
const handleSubmit = async (event) =>{
  event.preventDefault()
  const formData = new FormData()
  formData.append('file', fileInput.value.files[0])
  try {
    const response = await fetch('/upload', {
      method: 'POST',
      body: formData
    })
    if (response.ok) {
      const { session_id } = await response.json();
      const eventSource = new EventSource('/events?session_id=' + session_id)
      eventSource.addEventListener('start', (event) => {
        console.log('start', event.data)
        totalStudy.value = Math.floor(parseInt(event.data) / 2)
        totalAuthor.value = Math.ceil(parseInt(event.data) / 2)
        studyCheckboxes.value = Array.from({ length: totalStudy.value }, (_, i) => ({
          id: i + 1,
          checked: false
        }))
        authorCheckboxes.value = Array.from({ length: totalAuthor.value }, (_, i) => ({
          id: i + 1,
          checked: false
        }))
      })
      eventSource.addEventListener('received_study', (event) => {
        console.log('received_study', event.data)
        const data = JSON.parse(event.data)
        const id = parseInt(data.id) + 1
        const checkbox = studyCheckboxes.value.find((cb) => cb.id === id)
        if (checkbox) checkbox.checked = true
      })
      eventSource.addEventListener('received_author', (event) => {
        console.log('received_author', event.data)
        const data = JSON.parse(event.data)
        const id = parseInt(data.id) + 1
        const checkbox = authorCheckboxes.value.find((cb) => cb.id === id)
        if (checkbox) checkbox.checked = true
      })
      eventSource.addEventListener('done', (event) => {
        console.log('done', event.data)
        downloadLink.value = 'download/' + event.data
        eventSource.close()
      })
      eventSource.onerror = (error) => {
        console.error('EventSource error:', error)
        eventSource.close()
      }
    } else {
      alert('Failed to upload file')
    }
  } catch (error) {
    console.error(error)
    alert('Failed to upload file')
  }
};
</script>

<template>
  <div class="container mt-5">
    <!-- Title -->
    <div class="text-center mb-4">
      <h1 class="display-4 text-primary">InfluenceMapper</h1>
      <p class="lead text-muted">Upload your CSV file to start mapping your data.</p>
    </div>

    <!-- File Upload Form -->
    <div class="card shadow-sm p-4">
      <h3 class="card-title text-center mb-4">Upload CSV File</h3>
      <form @submit="handleSubmit" action="/upload" method="post" enctype="multipart/form-data">
        <div class="form-group">
          <label for="file" class="form-label">Choose CSV file:</label>
          <input type="file" id="file" name="file" accept=".csv" class="form-control" required ref="fileInput">
        </div>
        <div class="text-center mt-4">
          <button type="submit" class="btn btn-primary btn-lg">Upload</button>
        </div>
      </form>
    </div>

    <!-- Progress Section -->
    <div v-if="totalStudy > 0 || totalAuthor > 0" class="mt-5">
      <div class="row">
        <!-- Study Progress -->
        <div class="col-md-6">
          <div class="card shadow-sm">
            <div class="card-header bg-primary text-white">
              <h4 class="mb-0">Study Progress</h4>
            </div>
            <div class="card-body">
              <div class="form-check" v-for="checkbox in studyCheckboxes" :key="'study-' + checkbox.id">
                <input type="checkbox" class="form-check-input" :id="'study-' + checkbox.id" v-model="checkbox.checked" disabled>
                <label class="form-check-label" :for="'study-' + checkbox.id">Row {{ checkbox.id }}</label>
              </div>
            </div>
          </div>
        </div>

        <!-- Author Progress -->
        <div class="col-md-6">
          <div class="card shadow-sm">
            <div class="card-header bg-success text-white">
              <h4 class="mb-0">Author Progress</h4>
            </div>
            <div class="card-body">
              <div class="form-check" v-for="checkbox in authorCheckboxes" :key="'author-' + checkbox.id">
                <input type="checkbox" class="form-check-input" :id="'author-' + checkbox.id" v-model="checkbox.checked" disabled>
                <label class="form-check-label" :for="'author-' + checkbox.id">Row {{ checkbox.id }}</label>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Download Link -->
    <p v-if="downloadLink" class="mt-4 text-center">
      <strong>Download result:</strong>
      <a :href="downloadLink" target="_blank" class="btn btn-success btn-lg">{{ downloadLink }}</a>
    </p>
  </div>
</template>

<style scoped>
/* Add some custom styles */
.card {
  border-radius: 10px;
  border: none;
}

.card-header {
  border-radius: 10px 10px 0 0;
}

.card-body {
  padding: 1.5rem;
}

.text-center {
  text-align: center;
}
</style>
