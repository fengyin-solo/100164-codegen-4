<template>
  <section class="page" data-module="weather">
    <header class="page-head">
      <div>
        <h2>气象观测</h2>
        <p class="page-desc">录入观测时间、能见度、风速、风向与跑道视程；同一观测时刻重复录入自动合并；触及预警线即刻生成播报。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">录入气象实况</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="weather-layout">
      <div class="weather-panel">
        <h3 class="panel-title">观测记录（按观测时间倒序）</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>观测时间</th>
              <th>能见度(米)</th>
              <th>风速(米/秒)</th>
              <th>风向</th>
              <th>跑道视程(米)</th>
              <th>联带预警</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in observations"
              :key="String(row.id)"
              class="clickable-row"
              :class="{ 'row-alert': row.abnormal }"
              @click="openObservation(row.id)"
            >
              <td>{{ row['观测时间'] }}</td>
              <td>{{ row['能见度'] }}</td>
              <td>{{ row['风速'] }}</td>
              <td>{{ row['风向'] }}</td>
              <td>{{ row['跑道视程'] }}</td>
              <td>
                <span v-if="activeCount(row)" class="badge red">在播 {{ activeCount(row) }}</span>
                <span v-else-if="(row['预警播报'] ?? []).length" class="badge gray">已解除 {{ (row['预警播报'] ?? []).length }}</span>
                <span v-else class="muted-text">无</span>
              </td>
            </tr>
            <tr v-if="!observations.length">
              <td colspan="6" class="empty-state">暂无气象观测记录，可先录入一条气象实况</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="weather-panel">
        <h3 class="panel-title">预警播报清单（按播报时刻倒序）</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>播报时刻</th>
              <th>预警</th>
              <th>观测时间</th>
              <th>播报对象</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="alert in alerts"
              :key="String(alert.id)"
              class="clickable-row"
              @click="openObservation(alert['观测记录'])"
            >
              <td>{{ alert['播报时刻'] }}</td>
              <td>
                <span class="badge" :class="alert['预警等级'] === '红色' ? 'red' : 'orange'">
                  {{ alert['预警等级'] }}·{{ alert['预警类型'] }}
                </span>
              </td>
              <td>{{ alert['观测时间'] }}</td>
              <td>{{ alert['播报对象'] }}</td>
            </tr>
            <tr v-if="!alerts.length">
              <td colspan="4" class="empty-state">尚未产生预警播报</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <footer class="page-foot">
      <span>共 {{ observations.length }} 条观测记录、{{ alerts.length }} 条预警播报，数据保存在服务端，刷新后仍成立</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 录入弹窗 -->
    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <div class="modal-card">
        <h3>录入气象实况</h3>
        <p class="muted-text">观测时间精确到分钟；该时刻已有记录时将以本次数据合并覆盖，不会重复叠加。</p>
        <form class="weather-form" @submit.prevent="submitCreate">
          <label v-for="field in formFields" :key="field.key" class="form-item">
            <span>{{ field.label }}</span>
            <input
              v-model="form[field.key]"
              :type="field.type"
              :step="field.step"
              :placeholder="field.placeholder"
            />
          </label>
          <label class="form-item wide">
            <span>播报对象（可选，触发预警时记录，默认：{{ defaultTargets }}）</span>
            <input v-model="form['播报对象']" placeholder="如：塔台值班席、机坪管制" />
          </label>
          <div v-if="formError" class="error-text form-error">{{ formError }}</div>
          <div class="form-actions">
            <button class="btn ghost" type="button" @click="creating = false">取消</button>
            <button class="btn primary" type="submit" :disabled="submitting">{{ submitting ? '提交中…' : '保存实况' }}</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 明细弹窗 -->
    <div v-if="detail" class="modal-mask" @click.self="detail = null">
      <div class="modal-card wide-card">
        <h3>气象观测明细 #{{ detail.id }}</h3>
        <div class="detail-grid">
          <div v-for="field in detailFields" :key="field" class="detail-cell">
            <span class="detail-label">{{ field }}</span>
            <strong>{{ detail[field] ?? '—' }}</strong>
          </div>
          <div class="detail-cell">
            <span class="detail-label">观测状态</span>
            <strong>
              <span v-if="detail.abnormal" class="badge red">预警中</span>
              <span v-else class="badge green">正常</span>
            </strong>
          </div>
        </div>

        <h4 class="detail-sub">联带预警播报（共 {{ detail['预警播报']?.length ?? 0 }} 条，可与预警播报清单互相印证）</h4>
        <table v-if="detail['预警播报']?.length" class="data-table">
          <thead>
            <tr>
              <th>播报时刻</th>
              <th>预警</th>
              <th>触发实况</th>
              <th>预警阈值</th>
              <th>播报对象</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="alert in detail['预警播报']" :key="String(alert.id)">
              <td>{{ alert['播报时刻'] }}</td>
              <td>
                <span class="badge" :class="alert['预警等级'] === '红色' ? 'red' : 'orange'">
                  {{ alert['预警等级'] }}·{{ alert['预警类型'] }}
                </span>
                <div class="muted-text small">{{ alert['预警内容'] }}</div>
              </td>
              <td>{{ alert['触发实况'] }}</td>
              <td>{{ alert['预警阈值'] }}</td>
              <td>{{ alert['播报对象'] }}</td>
              <td>
                <span class="badge" :class="alert.status === '预警中' ? 'red' : 'gray'">{{ alert.status }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted-text">该观测未触发任何预警。</p>

        <div class="form-actions">
          <button class="btn primary" type="button" @click="detail = null">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

const ENDPOINT = '/api/weather'
const defaultTargets = '塔台、机坪管制、运行指挥中心'

type AlertRow = {
  id: number
  观测记录: number
  观测时间: string
  预警类型: string
  预警等级: string
  触发实况: string
  预警阈值: string
  预警内容: string
  播报对象: string
  播报时刻: string
  status: string
}
type ObservationRow = {
  id: number
  观测时间: string
  能见度: number
  风速: number
  风向: string
  跑道视程: number
  status: string
  abnormal: boolean
  预警播报?: AlertRow[]
  [key: string]: string | number | boolean | AlertRow[] | undefined
}

const observations = ref<ObservationRow[]>([])
const alerts = ref<AlertRow[]>([])
const errorMessage = ref('')
const creating = ref(false)
const submitting = ref(false)
const formError = ref('')
const detail = ref<ObservationRow | null>(null)

const formFields = [
  { key: '观测时间', label: '观测时间', type: 'datetime-local', step: 60, placeholder: '' },
  { key: '能见度', label: '能见度（米，0～10000）', type: 'number', step: 1, placeholder: '如 1200' },
  { key: '风速', label: '风速（米/秒，0～100）', type: 'number', step: 0.1, placeholder: '如 6.5' },
  { key: '风向', label: '风向（0～360 度或西北风等十六方位）', type: 'text', step: '', placeholder: '如 270 或 西北风' },
  { key: '跑道视程', label: '跑道视程（米，0～2000）', type: 'number', step: 1, placeholder: '如 600' },
] as const

const form = reactive<Record<string, string>>({
  观测时间: '',
  能见度: '',
  风速: '',
  风向: '',
  跑道视程: '',
  播报对象: '',
})

const detailFields = ['观测时间', '能见度', '风速', '风向', '跑道视程']

const stats = computed(() => {
  const active = alerts.value.filter((a) => a.status === '预警中')
  const red = active.filter((a) => a['预警等级'] === '红色').length
  return [
    { label: '观测记录', value: observations.value.length },
    { label: '预警总数', value: alerts.value.length },
    { label: '在播预警', value: active.length },
    { label: '红色在播', value: red },
  ]
})

function activeCount(row: ObservationRow): number {
  return (row['预警播报'] ?? []).filter((a) => a.status === '预警中').length
}

function openCreate() {
  formError.value = ''
  Object.keys(form).forEach((key) => { form[key] = '' })
  creating.value = true
}

async function submitCreate() {
  formError.value = ''
  submitting.value = true
  try {
    const values: Record<string, string> = {}
    for (const key of ['观测时间', '能见度', '风速', '风向', '跑道视程']) {
      values[key] = form[key]?.trim() ?? ''
    }
    if (form['播报对象']?.trim()) {
      values['播报对象'] = form['播报对象'].trim()
    }
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      formError.value = payload.detail || payload.message || '气象实况未保存'
      return
    }
    creating.value = false
    await reload()
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '气象实况保存失败'
  } finally {
    submitting.value = false
  }
}

async function openObservation(id: number) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) {
      throw new Error(`观测明细读取失败（${response.status}）`)
    }
    detail.value = (await response.json()) as ObservationRow
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '观测明细读取失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const [obsResp, alertResp] = await Promise.all([
      request(ENDPOINT),
      request(`${ENDPOINT}/alerts`),
    ])
    if (!obsResp.ok || !alertResp.ok) {
      throw new Error('气象数据读取失败')
    }
    const obsPayload = await obsResp.json()
    const alertPayload = await alertResp.json()
    observations.value = (obsPayload.items ?? []) as ObservationRow[]
    alerts.value = (alertPayload.items ?? []) as AlertRow[]
    // 明细弹窗若仍开着，跟随最新数据刷新，保证与观测清单口径一致
    if (detail.value) {
      const refreshed = observations.value.find((row) => row.id === detail.value?.id)
      if (refreshed) {
        detail.value = refreshed
      }
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '气象数据读取失败'
  }
}

onMounted(reload)
</script>
