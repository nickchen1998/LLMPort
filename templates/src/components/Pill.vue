<script setup>
defineProps({ c: String, t: String })
</script>

<template>
  <span class="pill" :class="'p-' + c"><i></i>{{ t }}</span>
</template>
