<template>
  <div class="license-page">
    <div class="license-container">
      <!-- Header -->
      <div class="license-header">
        <div class="license-logo">J</div>
        <div>
          <h1 class="license-title">软件使用许可协议</h1>
          <p class="license-subtitle">九洲 RAG 知识管理平台 v1.0.0</p>
        </div>
      </div>

      <!-- Copyright Notice -->
      <section class="license-section">
        <h2 class="section-title">版权声明</h2>
        <p>本软件由<strong>四川九洲电器集团有限责任公司 707部</strong>自主开发，保留所有权利。</p>
        <p>Copyright © 2024-2026 四川九洲电器集团有限责任公司 707部。All Rights Reserved.</p>
      </section>

      <!-- License Terms -->
      <section class="license-section">
        <h2 class="section-title">使用许可</h2>
        <p>本平台软件（以下称"本软件"）仅授权于经授权的内部用户使用，不得用于以下目的：</p>
        <ul class="license-list">
          <li>出售、转让、再授权或以任何形式向第三方分发本软件；</li>
          <li>对本软件进行逆向工程、反编译或分解；</li>
          <li>移除或修改本软件中的任何版权声明或标识；</li>
          <li>将本软件用于任何违法或违规活动。</li>
        </ul>
      </section>

      <!-- Open Source Components -->
      <section class="license-section">
        <h2 class="section-title">开源组件声明</h2>
        <p>本软件使用了以下开源组件，对其作者和社区表示感谢：</p>
        <div class="oss-grid">
          <div class="oss-item" v-for="lib in ossDeps" :key="lib.name">
            <span class="oss-name">{{ lib.name }}</span>
            <span class="oss-license">{{ lib.license }}</span>
          </div>
        </div>
      </section>

      <!-- Disclaimer -->
      <section class="license-section">
        <h2 class="section-title">免责声明</h2>
        <p>本软件按"现状"提供，四川九洲电器集团 707部不对使用本软件所产生的任何直接或间接损失承担责任，包括但不限于数据丢失、商业利润损失等。</p>
        <p>用户需自行确保在合法、合规的前提下使用本软件，并对自己的操作结果负责。</p>
      </section>

      <!-- Contact -->
      <section class="license-section">
        <h2 class="section-title">联系方式</h2>
        <p>如有使用许可相关问题，请联系：<strong>四川九洲电器集团有限责任公司 707部</strong></p>
      </section>

      <!-- Back -->
      <div class="license-footer">
        <button class="back-btn" @click="$router.back()">← 返回</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const ossDeps = [
  { name: 'FastAPI', license: 'MIT License' },
  { name: 'Vue 3', license: 'MIT License' },
  { name: 'ChromaDB', license: 'Apache 2.0' },
  { name: 'LangChain', license: 'MIT License' },
  { name: 'Element Plus', license: 'MIT License' },
  { name: 'PyMuPDF', license: 'AGPL / Commercial' },
  { name: 'Playwright', license: 'Apache 2.0' },
  { name: 'httpx', license: 'BSD License' },
  { name: 'Sentence Transformers', license: 'Apache 2.0' },
  { name: 'jieba', license: 'MIT License' },
]
</script>

<style scoped>
.license-page {
  height: 100%;
  overflow: auto;
  padding: var(--sp-6);
  animation: pageEnter 0.4s var(--ease);
}

@keyframes pageEnter {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.license-container {
  max-width: 720px;
  margin: 0 auto;
}

.license-header {
  display: flex;
  align-items: center;
  gap: var(--sp-4);
  margin-bottom: var(--sp-8);
  padding-bottom: var(--sp-6);
  border-bottom: 1px solid var(--c-border);
}

.license-logo {
  width: 48px;
  height: 48px;
  background: linear-gradient(135deg, rgba(255,255,255,0.15), rgba(255,255,255,0.05));
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 20px;
  color: var(--c-text-primary);
  flex-shrink: 0;
}

.license-title {
  font-size: var(--fs-xl);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-1);
  letter-spacing: -0.5px;
}

.license-subtitle {
  font-size: var(--fs-sm);
  color: var(--c-text-tertiary);
  margin: 0;
}

.license-section {
  margin-bottom: var(--sp-6);
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius);
  padding: var(--sp-5) var(--sp-6);
}

.section-title {
  font-size: var(--fs-base);
  font-weight: 600;
  color: var(--c-text-primary);
  margin: 0 0 var(--sp-4);
  padding-bottom: var(--sp-3);
  border-bottom: 1px solid var(--c-border);
}

.license-section p {
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
  line-height: 1.7;
  margin: 0 0 var(--sp-3);
}

.license-section p:last-child {
  margin-bottom: 0;
}

.license-list {
  font-size: var(--fs-sm);
  color: var(--c-text-secondary);
  line-height: 1.7;
  padding-left: var(--sp-5);
  margin: 0;
}

.license-list li {
  margin-bottom: var(--sp-2);
}

.oss-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--sp-2);
}

.oss-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--sp-2) var(--sp-3);
  background: var(--c-surface);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
}

.oss-name {
  font-size: var(--fs-xs);
  font-weight: 500;
  color: var(--c-text-primary);
}

.oss-license {
  font-size: 10px;
  color: var(--c-text-tertiary);
}

.license-footer {
  padding: var(--sp-4) 0 var(--sp-8);
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 0 var(--sp-5);
  height: var(--btn-h);
  background: var(--glass-bg);
  border: 1px solid var(--c-border);
  border-radius: var(--radius-sm);
  color: var(--c-text-secondary);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition: all var(--duration) var(--ease);
}

.back-btn:hover {
  background: var(--c-surface-hover);
  color: var(--c-text-primary);
}
</style>
