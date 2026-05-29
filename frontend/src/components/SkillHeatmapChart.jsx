/**
 * SkillHeatmapChart — 技能利用热力图
 * X 轴 = 工作流步骤，Y 轴 = Skills，颜色深浅 = 利用率
 */
import { Cell, Tooltip, XAxis, YAxis, BarChart, Bar, ResponsiveContainer, Legend } from 'recharts'

const RATE_COLORS = (rate) => {
  if (rate >= 0.8) return '#52c41a'
  if (rate >= 0.5) return '#faad14'
  if (rate > 0) return '#fa8c16'
  return '#d9d9d9'
}

export default function SkillHeatmapChart({ heatmap, steps }) {
  if (!heatmap || Object.keys(heatmap).length === 0) {
    return null
  }

  // 提取所有唯一 skills
  const allSkills = new Set()
  Object.values(heatmap).forEach(stepHeat => {
    Object.keys(stepHeat).forEach(sk => allSkills.add(sk))
  })
  const skills = [...allSkills]

  if (skills.length === 0) return null

  // 构建数据: 每行一个 skill，每列一个 step
  const data = skills.map(skill => {
    const row = { skill }
    Object.entries(heatmap).forEach(([stepId, stepHeat]) => {
      const stepName = steps?.find(s => s.step_id === stepId)?.step_name || stepId
      row[stepName] = stepHeat[skill] ?? 0
    })
    return row
  })

  // 步骤列名
  const stepNames = Object.keys(heatmap).map(stepId => {
    return steps?.find(s => s.step_id === stepId)?.step_name || stepId
  })

  const COLORS = ['#1890ff', '#52c41a', '#faad14', '#ff4d4f', '#722ed1', '#13c2c2']

  return (
    <ResponsiveContainer width="100%" height={Math.max(200, skills.length * 30 + 40)}>
      <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
        <XAxis type="number" domain={[0, 1]} tickFormatter={v => `${Math.round(v * 100)}%`} />
        <YAxis
          type="category"
          dataKey="skill"
          width={140}
          tick={{ fontSize: 11 }}
        />
        <Tooltip
          formatter={(value, name) => [`${Math.round(value * 100)}%`, name]}
        />
        <Legend />
        {stepNames.map((name, i) => (
          <Bar
            key={name}
            dataKey={name}
            fill={COLORS[i % COLORS.length]}
            barSize={16}
            radius={[0, 4, 4, 0]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}
