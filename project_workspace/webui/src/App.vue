<!--
  MOD-WEB-F01: Root App component.
  Only contains <router-view /> — layout is determined by route meta.
-->
<template>
  <router-view />
</template>

<script setup lang="ts">
// App root component — routing is handled by Vue Router
</script>

<style>
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', Arial, sans-serif;
}
</style>
