<template>
  <section class="page" data-module="weather">
    <header class="page-head">
      <div>
        <h2>气象观测</h2>
        <p class="page-desc">录入观测时间、能见度、风速、风向与跑道视程；记录按观测时间倒序排列，达到预警线自动生成预警播报。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">录入气象实况</button>
        <button class="btn" type="button" @click="exportRows">导出观测清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="filter-bar">
      <label class="filter-item switch-item">
        <input v-model="warningOnly" type="checkbox" @change="reload" />
        <span>只看预警观测</span>
      </label>
      <button class="btn ghost" type="button" @click="reload">刷新</button>
    </div>

    <div class="panel-grid">
      <div class="panel">
        <h3 class="panel-title">观测记录（时间倒序）</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>观测时间</th>
              <th>能见度(米)</th>
              <th>风速(米/秒)</th>
              <th>风向</th>
              <th>跑道视程(米)</th>
              <th>状态</th>
              <th>明细</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="String(row.id)" :class="{ 'warn-row': row.预警播报 }">
              <td>{{ row.观测时间 }}</td>
              <td>{{ formatNum(row.能见度) }}</td>
              <td>{{ formatNum(row.风速) }}</td>
              <td>{{ row.风向 }}</td>
              <td>{{ row.跑道视程 == null ? '—' : formatNum(row.跑道视程) }}</td>
              <td>
                <span v-if="row.预警播报" class="badge warn">预警</span>
                <span v-else class="badge ok">正常</span>
              </td>
              <td><button class="link" type="button" @click="openDetail(row.id)">查看明细</button></td>
            </tr>
            <tr v-if="!rows.length">
              <td colspan="7" class="empty-state">暂无气象观测记录，可先录入气象实况</td>
            </tr>
          </tbody>
        </table>
        <footer class="page-foot"><span>共 {{ total }} 条观测记录</span></footer>
      </div>

      <div class="panel">
        <h3 class="panel-title">预警播报清单（播报时刻倒序）</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>播报编号</th>
              <th>观测时间</th>
              <th>播报时刻</th>
              <th>播报对象</th>
              <th>来源记录</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="bc in broadcasts" :key="bc.播报编号">
              <td>{{ bc.播报编号 }}</td>
              <td>{{ bc.观测时间 }}</td>
              <td>{{ bc.播报时刻 }}</td>
              <td>{{ bc.播报对象 }}</td>
              <td>
                <button class="link" type="button" @click="openDetail(bc.观测记录)">
                  #{{ bc.观测记录 }}
                </button>
              </td>
            </tr>
            <tr v-if="!broadcasts.length">
              <td colspan="5" class="empty-state">暂无预警播报</td>
            </tr>
          </tbody>
        </table>
        <footer class="page-foot"><span>共 {{ broadcasts.length }} 条预警播报，均可回溯到左侧观测记录</span></footer>
      </div>
    </div>

    <footer class="page-foot">
      <span v-if="successMessage" class="ok-text">{{ successMessage }}</span>
      <span v-else>数据持久保存在后端，刷新页面后记录与播报仍然成立</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 录入弹层 -->
    <div v-if="creating" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <h3>录入气象实况</h3>
        <p class="modal-tip">同一观测时间重复录入会合并更新，不会产生两条记录。</p>
        <form @submit.prevent="submitCreate">
          <label class="form-item">
            <span>观测时间 *</span>
            <input v-model="form.观测时间" type="datetime-local" required />
          </label>
          <label class="form-item">
            <span>能见度（米，0~10000）*</span>
            <input v-model="form.能见度" type="number" min="0" max="10000" step="1" placeholder="如 2500" required />
          </label>
          <label class="form-item">
            <span>风速（米/秒，0~75）*</span>
            <input v-model="form.风速" type="number" min="0" max="75" step="0.1" placeholder="如 4.5" required />
          </label>
          <label class="form-item">
            <span>风向 *</span>
            <input v-model="form.风向" list="wind-dir-list" placeholder="如 东北风" required />
            <datalist id="wind-dir-list">
              <option v-for="d in windDirections" :key="d" :value="d"></option>
            </datalist>
          </label>
          <label class="form-item">
            <span>跑道视程（米，0~3000，可空缺）</span>
            <input v-model="form.跑道视程" type="number" min="0" max="3000" step="1" placeholder="未观测可留空" />
          </label>
          <p class="modal-hint">预警线：能见度低于 800 米 / 风速达到 17 米/秒 / 跑道视程低于 550 米</p>
          <p v-if="formError" class="error-text form-error">{{ formError }}</p>
          <div class="modal-actions">
            <button class="btn" type="button" @click="closeCreate">取消</button>
            <button class="btn primary" type="submit" :disabled="submitting">{{ submitting ? '保存中…' : '保存' }}</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 明细弹层 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal">
        <h3>观测明细 #{{ detail.id }}</h3>
        <dl class="detail-grid">
          <div><dt>观测时间</dt><dd>{{ detail.观测时间 }}</dd></div>
          <div><dt>能见度</dt><dd>{{ formatNum(detail.能见度) }} 米</dd></div>
          <div><dt>风速</dt><dd>{{ formatNum(detail.风速) }} 米/秒</dd></div>
          <div><dt>风向</dt><dd>{{ detail.风向 }}</dd></div>
          <div><dt>跑道视程</dt><dd>{{ detail.跑道视程 == null ? '未观测' : `${formatNum(detail.跑道视程)} 米` }}</dd></div>
          <div><dt>录入次数</dt><dd>{{ detail.录入次数 ?? 1 }} 次（同时刻重复录入已合并）</dd></div>
          <div><dt>观测状态</dt><dd>{{ detail.预警播报 ? '达到预警线' : '正常' }}</dd></div>
        </dl>
        <div v-if="detail.预警播报" class="broadcast-box">
          <h4>预警播报</h4>
          <p class="broadcast-content">{{ detail.预警播报.预警内容 }}</p>
          <dl class="detail-grid">
            <div><dt>播报编号</dt><dd>{{ detail.预警播报.播报编号 }}</dd></div>
            <div><dt>播报时刻</dt><dd>{{ detail.预警播报.播报时刻 }}</dd></div>
            <div><dt>播报对象</dt><dd>{{ detail.预警播报.播报对象 }}</dd></div>
          </dl>
        </div>
        <div v-else class="no-broadcast">该观测未达到预警线，暂无预警播报。</div>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/weather'

type Broadcast = {
  播报编号: string
  观测时间: string
  播报时刻: string
  播报对象: string
  预警内容: string
  观测记录: number
}

type Row = {
  id: number
  观测时间: string
  能见度: number | null
  风速: number | null
  风向: string
  跑道视程: number | null
  录入次数?: number
  status?: string
  预警播报?: (Broadcast & { 触发原因?: string[] }) | null
}

const rows = ref<Row[]>([])
const broadcasts = ref<Broadcast[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const warningOnly = ref(false)

const creating = ref(false)
const submitting = ref(false)
const formError = ref('')
const form = ref<Record<string, string>>({ 观测时间: '', 能见度: '', 风速: '', 风向: '', 跑道视程: '' })
const windDirections = ['北风', '东北风', '东风', '东南风', '南风', '西南风', '西风', '西北风']

const detail = ref<Row | null>(null)

const stats = computed(() => {
  const warnCount = rows.value.filter((r) => r.预警播报).length
  return [
    { label: '观测记录数', value: total.value },
    { label: '当前页预警', value: warnCount },
    { label: '累计播报', value: broadcasts.value.length },
  ]
})

function formatNum(value: number | null | undefined): string {
  if (value == null) return '—'
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(2)))
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  form.value = { 观测时间: '', 能见度: '', 风速: '', 风向: '', 跑道视程: '' }
  formError.value = ''
  creating.value = true
}

function closeCreate() {
  creating.value = false
}

async function submitCreate() {
  formError.value = ''
  errorMessage.value = ''
  successMessage.value = ''
  submitting.value = true
  try {
    const values: Record<string, string> = {
      观测时间: form.value.观测时间,
      能见度: form.value.能见度,
      风速: form.value.风速,
      风向: form.value.风向,
    }
    if (form.value.跑道视程.trim()) {
      values.跑道视程 = form.value.跑道视程
    }
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '气象观测保存失败')
    }
    successMessage.value = payload.message
    creating.value = false
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '气象观测保存失败'
  } finally {
    submitting.value = false
  }
}

async function openDetail(id: number) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) {
      throw new Error('观测明细读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测明细读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = warningOnly.value ? '?warning=1' : ''
  try {
    const [listRes, bcRes] = await Promise.all([
      request(`${ENDPOINT}${query}`),
      request(`${ENDPOINT}/broadcasts`),
    ])
    if (!listRes.ok || !bcRes.ok) {
      throw new Error('气象数据读取失败')
    }
    const listPayload = await listRes.json()
    const bcPayload = await bcRes.json()
    rows.value = listPayload.items ?? []
    total.value = listPayload.total ?? rows.value.length
    broadcasts.value = bcPayload.items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '气象数据读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.panel-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 12px;
}
.panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.panel-title {
  margin: 0 0 8px;
  font-size: 14px;
}
.switch-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.switch-item span {
  color: inherit;
}
.warn-row {
  background: #fef3f2;
}
.badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 12px;
}
.badge.warn {
  background: #fee4e2;
  color: #b42318;
}
.badge.ok {
  background: #e7f6ec;
  color: #067647;
}
.ok-text {
  color: #067647;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.modal {
  background: #fff;
  border-radius: 10px;
  width: 560px;
  max-width: calc(100vw - 32px);
  max-height: calc(100vh - 64px);
  overflow-y: auto;
  padding: 18px 20px;
}
.modal h3 {
  margin: 0 0 6px;
  font-size: 16px;
}
.modal-tip {
  margin: 0 0 12px;
  color: var(--muted);
  font-size: 12px;
}
.form-item {
  display: block;
  margin-bottom: 10px;
}
.form-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.form-item input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}
.modal-hint {
  font-size: 12px;
  color: var(--muted);
  margin: 6px 0;
}
.form-error {
  margin: 6px 0;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
  margin: 10px 0;
}
.detail-grid dt {
  font-size: 12px;
  color: var(--muted);
}
.detail-grid dd {
  margin: 2px 0 0;
  font-size: 13px;
}
.broadcast-box {
  border: 1px solid #f5c2c0;
  background: #fef3f2;
  border-radius: 8px;
  padding: 10px 12px;
  margin-top: 8px;
}
.broadcast-box h4 {
  margin: 0 0 6px;
  font-size: 13px;
  color: #b42318;
}
.broadcast-content {
  margin: 0 0 8px;
  font-size: 13px;
}
.no-broadcast {
  color: var(--muted);
  font-size: 13px;
  padding: 10px 0;
}
</style>
