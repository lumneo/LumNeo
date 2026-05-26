<template>
  <n-drawer :show="show" :auto-focus="false" @update:show="(val: boolean) => emit('update:show', val)" width="400">
    <n-drawer-content title="设置" closable>
      <n-tabs default-value="model">
        <n-tab-pane name="model" tab="模型管理">
          <n-space vertical>
            <!-- 当前活跃模型指示 -->
            <n-alert v-if="!configStore.activeModel" type="warning" title="尚未选择模型" />
            <div v-else>
              <n-tag type="info" size="small">当前使用：{{ configStore.activeModel.name }}</n-tag>
            </div>

            <n-divider />

            <!-- 模型列表 -->
            <n-list hoverable clickable>
              <n-list-item v-for="model in configStore.savedModels" :key="model.id">
                <template #suffix>
                  <n-space>
                    <n-button text size="small" @click="editModel(model)">编辑</n-button>
                    <n-popconfirm 
                    @positive-click="() => configStore.deleteModel(model.id)" 
                    negative-text="取消" 
                    positive-text="好的"
                    :negative-button-props="{size: 'tiny'}"
                    :positive-button-props="{size: 'tiny'}"
                    >
                      <template #trigger>
                        <n-button text size="small" type="error">删除</n-button>
                      </template>
                      确定删除模型「{{ model.name }}」吗？
                    </n-popconfirm>
                  </n-space>
                </template>
                <div>
                  <n-text strong>{{ model.name }}</n-text>
                  <n-text depth="3"> · {{ model.type === 'local' ? '本地' : '云端' }}</n-text>
                  <br />
                  <n-text depth="3" style="font-size: 0.8rem">{{ model.modelName }}</n-text>
                </div>
              </n-list-item>
            </n-list>

            <n-button type="primary" block @click="openAddModelDialog">添加模型</n-button>
          </n-space>


        </n-tab-pane>

        <!-- 其他设置 -->
        <n-tab-pane name="function" tab="功能设置">
          <n-form label-placement="left" label-width="80">
            <n-form-item label="启用角色">
              <n-switch v-model:value="chatStore.enableProfile" @update-value="handleProfile"/>
            </n-form-item>
            <n-form-item label="主题">
              <n-button @click="configStore.toggleTheme">
                <template #icon>
                  <n-icon><m-svg :name="configStore.themeMode === 'dark' ? 'moon' : 'son'"/></n-icon>
                </template>
                {{ configStore.themeMode === 'dark' ? '暗色' : '浅色' }}
              </n-button>
            </n-form-item>
            <n-form-item label="工作目录">
              <n-flex>
                <n-input style="width:70%" v-model:value="workspacePath" placeholder="选择或输入目录路径" @change="saveWorkspace(workspacePath)"/>
                <n-button text @click="selectFolder">选择目录</n-button>
              </n-flex>
            </n-form-item>
          </n-form>

          <!-- ========== 角色管理 ========== -->
          <div v-if="chatStore.enableProfile">
            <n-divider />
            <h3 style="margin-bottom: 12px;">角色管理</h3>
            <n-select
              v-model:value="profileStore.activeProfileId"
              :options="profileOptions"
              placeholder="选择角色"
              clearable
              style="margin-bottom: 12px;"
            />
            <n-space>
              <n-button @click="openCreateProfile" size="small" secondary type="primary">新建角色</n-button>
              <n-button @click="openEditProfile" size="small" secondary :disabled="!profileStore.activeProfile">编辑</n-button>
              <n-button @click="deleteCurrentProfile" size="small" secondary type="error" :disabled="!profileStore.activeProfile">删除</n-button>
            </n-space>
          </div>
        </n-tab-pane>
      </n-tabs>
    </n-drawer-content>
  </n-drawer>

  <!-- 新增/编辑模型对话框 -->
  <n-modal v-model:show="showModelDialog" :auto-focus="false" preset="dialog" draggable :mask-closable="false" :loading="configStore.loading" :title="editingModelId ? '编辑模型' : '添加模型'"
    positive-text="保存" negative-text="取消" @positive-click="saveModel">
    <n-form :model="modelForm" label-placement="left" label-width="80">
      <n-form-item label="名称" required>
        <n-input v-model:value="modelForm.name" placeholder="例如：我的 GPT-4" />
      </n-form-item>
      <n-form-item label="类型">
        <n-radio-group v-model:value="modelForm.type">
          <n-radio value="local">本地模型</n-radio>
          <n-radio value="online">线上模型</n-radio>
        </n-radio-group>
      </n-form-item>
      <n-form-item label="模型 ID" required>
        <n-space>
          <n-select
            style="width: 240px"
            v-model:value="modelForm.modelName"
            :options="modelOptions"
            filterable
            placeholder="请选择或输入模型名称"
            :loading="modelsLoading"
            @focus="autoFetchModels"
          />
          <n-button @click="fetchModels">获取</n-button>
        </n-space>
      </n-form-item>
      <n-form-item label="Base URL">
        <n-input v-model:value="modelForm.baseUrl" placeholder="http://localhost:1234/v1" />
      </n-form-item>
      <n-form-item label="API Key">
        <n-input v-model:value="modelForm.apiKey" type="password" placeholder="sk-..." />
      </n-form-item>
    </n-form>
  </n-modal>

  <!-- 新建/编辑角色模态框 -->
  <n-modal 
  v-model:show="profileModalVisible" 
  :auto-focus="false"
  preset="dialog" 
  draggable
  :mask-closable="false"
  style="max-width:520px;width:96%;" 
  :title="isEditing ? '编辑角色' : '新建角色'"
  positive-text="确认"
  negative-text="关闭"
  @positive-click="saveProfile"
  @negative-click="profileModalVisible = false">
    <n-form :model="profileForm" label-placement="left" label-width="70">
      <n-form-item label="角色名称">
        <n-input v-model:value="profileForm.name" placeholder="例如：程序员、生活助手" :maxlength="12" show-count/>
      </n-form-item>
      <n-form-item label="角色描述">
        <n-input
          v-model:value="profileForm.profile_prompt"
          type="textarea"
          placeholder="例如：你是一个专业的 Python 开发者，回答要简洁..."
          show-count
          :maxlength="300"
          :autosize="{ minRows: 3, maxRows: 8 }"
        />
      </n-form-item>
      <n-form-item label="赋予能力">
        <n-button size="small" style="position:absolute;left:-64px;top:40px;" @click="loadTools">刷新</n-button>
        <div style="width: 420px; max-height: 40vh; overflow-y: auto;">
          <n-checkbox-group v-model:value="profileForm.tools">
            <n-space vertical>
              <n-checkbox v-for="tool in allTools" :key="tool.function.name" :value="tool.function.name">
                <n-popover trigger="hover" placement="right" :width="400">
                  <template #trigger>
                    <span style="cursor: pointer;">{{ tool.function.name }}</span>
                  </template>
                  <div style="word-break: break-word; white-space: pre-wrap;">
                    {{ tool.function.description }}
                  </div>
                </n-popover>
              </n-checkbox>
            </n-space>
          </n-checkbox-group>
        </div>
        <p v-if="allTools.length === 0" style="color: gray;">暂无可用工具，请检查 MCP 服务或工具配置。</p>
      </n-form-item>
    </n-form>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, computed } from 'vue'
import {
  NDrawer, NDrawerContent, NForm, NFormItem, NInput, NPopover, NFlex,
  NRadioGroup, NRadio, NSwitch, NButton, NSpace, NDivider, NIcon,
  NTabs, NTabPane, NList, NListItem, NPopconfirm, NTag, NAlert, 
  NModal, NSelect, NCheckboxGroup, NCheckbox, NText, useMessage
} from 'naive-ui'
import { useChatStore } from '@/stores/chat'
import { useConfigStore, type ModelConfig } from '@/stores/config'
import { useProfileStore, type Profile } from '@/stores/profiles'
import mSvg from '@/components/MSvg.vue'


const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ 'update:show': [value: boolean] }>()

const message = useMessage()
const chatStore = useChatStore()
const configStore = useConfigStore()
const profileStore = useProfileStore()


// 对话框状态
const showModelDialog = ref(false)
const editingModelId = ref<string | null>(null)
const modelForm = reactive<{
  name: string
  type: 'local' | 'online'
  modelName?: string
  baseUrl: string
  apiKey: string
}>({
  name: '',
  type: 'local',
  modelName: undefined,
  baseUrl: '',
  apiKey: ''
})

function handleProfile(val: boolean) {
  localStorage.setItem('enableProfile', val.toString())
}

function openAddModelDialog() {
  editingModelId.value = null
  modelForm.name = ''
  modelForm.type = 'local'
  modelForm.modelName = undefined
  modelForm.baseUrl = ''
  modelForm.apiKey = ''
  showModelDialog.value = true
}

function editModel(model: ModelConfig) {
  editingModelId.value = model.id
  modelForm.name = model.name
  modelForm.type = model.type
  modelForm.modelName = model.modelName
  modelForm.baseUrl = model.baseUrl
  modelForm.apiKey = model.apiKey || ''
  showModelDialog.value = true
}

const modelOptions = ref<{ label: string; value: string }[]>([])
const modelsLoading = ref(false)

async function fetchModels() {
  if (modelsLoading.value) return
  if (!modelForm.baseUrl) {
    message.warning('请先填写 Base URL')
    return
  }
  modelsLoading.value = true
  try {
    const res = await fetch('/api/model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: modelForm.baseUrl,
        api_key: modelForm.apiKey || ''
      })
    })
    const data = await res.json()
    if(data.detail) {
      message.error("请正确填写API Key")
      modelOptions.value = []
      return
    }
    modelOptions.value = data.map((id: string) => ({ label: id, value: id }))
    if (data.length === 0) {
      message.info('未检测到可用模型，请检查服务或手动输入')
    }
  } catch (e) {
    message.error('获取模型列表失败')
  } finally {
    modelsLoading.value = false
  }
}

// 当 baseUrl 或 apiKey 改变时，可自动刷新（可选）
watch(() => [modelForm.baseUrl, modelForm.apiKey], () => {
  modelOptions.value = []
})

// 在打开添加/编辑对话框时，若已有 baseUrl 可自动拉取
watch(showModelDialog, (show) => {
  if (show && modelForm.baseUrl) {
    autoFetchModels()
  }
})

function autoFetchModels() {
  if (!modelOptions.value.length && modelForm.baseUrl) {
    fetchModels()
  }
}

function saveModel() {
  if ( !modelForm.modelName || (!modelForm.name.trim() || !modelForm.modelName.trim())) {
    message.warning('名称和模型 ID 不能为空')
    return false
  }
  if (editingModelId.value) {
    configStore.updateModel(editingModelId.value, { ...modelForm })
  } else {
    configStore.addModel({ ...modelForm })
  }
  showModelDialog.value = false
}

const workspacePath = ref(localStorage.getItem('workspacePath') || '')
async function selectFolder() {
  try {
    // @ts-ignore
    const folder = await window.pywebview.api.select_folder()
    if (folder) {
      workspacePath.value = folder
      localStorage.setItem('workspacePath', folder)
      await saveWorkspace(folder)
    }
  } catch {
   message.warning('文件夹选择仅支持桌面环境')
  }
}

async function getWorkspace() {
  try {
    const res = await fetch('/api/workspace')
    const data = await res.json()
    if (data.path) {
      workspacePath.value = data.path
      localStorage.setItem('workspacePath', data.path)
    }
  } catch (e) {
    console.warn('获取工作目录失败', e)
  }
}

async function saveWorkspace(path: string, isMsg: boolean = true) {
  await fetch('/api/workspace/set', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path })
  }).then(async (res: any) => {
    if (res.ok) {
      if (isMsg)
        message.success('工作目录设置成功')
        localStorage.setItem('workspacePath', path)
    } else {
      const errorData = await res.json()
      message.error(errorData.detail || '工作目录设置失败')
    }
  })
}

// ---------- 角色管理 ----------
const allTools = ref<{ function: { name: string; description: string } }[]>([])

// 加载全局工具列表
async function loadTools() {
  try {
    const res = await fetch('/api/tools')
    const data = await res.json()
    allTools.value = data.tools || []
  } catch (e) {
    console.warn('获取工具列表失败', e)
  }
}

// 角色相关状态
const profileModalVisible = ref(false)
const isEditing = ref(false)
const editingProfile = ref<Profile | null>(null)
const profileForm = reactive({ name: '', tools: [] as string[], profile_prompt: '' })

const profileOptions = computed(() =>
  profileStore.profiles.map(p => ({ label: p.name, value: p.id }))
)

function openCreateProfile() {
  if(allTools.value.length === 0) {
    loadTools()
  }
  isEditing.value = false
  editingProfile.value = null
  profileForm.name = ''
  profileForm.tools = []
  profileModalVisible.value = true
  profileForm.profile_prompt = ''
}

function openEditProfile() {
  if (!profileStore.activeProfile) return
  if(allTools.value.length === 0) {
    loadTools()
  }
  isEditing.value = true
  editingProfile.value = { ...profileStore.activeProfile }
  profileForm.name = editingProfile.value.name
  profileForm.tools = [...editingProfile.value.tools]
  profileModalVisible.value = true
  profileForm.profile_prompt = editingProfile.value.profile_prompt || ''
}

async function saveProfile() {
  if (isEditing.value && editingProfile.value) {
    await profileStore.updateProfile(editingProfile.value.id, profileForm.name, profileForm.tools, profileForm.profile_prompt)
  } else {
    await profileStore.createProfile(profileForm.name, profileForm.tools, profileForm.profile_prompt)
  }
  profileModalVisible.value = false
}

async function deleteCurrentProfile() {
  if (profileStore.activeProfile) {
    await profileStore.deleteProfile(profileStore.activeProfile.id)
  }
}

onMounted(() => {
  configStore.loadModels()
  if (!workspacePath.value) {
    getWorkspace()
  } else {
    saveWorkspace(workspacePath.value, false)
  }
})
</script>