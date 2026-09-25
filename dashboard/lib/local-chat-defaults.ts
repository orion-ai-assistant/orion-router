import catalog from '../../data/models.json';

const defaults = catalog.models.find((model) => model.provider === 'local' && model.capability === 'chat');
if (!defaults?.settings?.local_sampling || defaults.temperature === undefined) {
  throw new Error('models.json needs local chat defaults');
}

export const localTemperatureDefault = defaults.temperature;
export const localSamplingDefaults = defaults.settings.local_sampling;
export type LocalSamplingKey = keyof typeof localSamplingDefaults;

export const localSamplingInputDefaults: Record<LocalSamplingKey, string> = {
  top_p: String(localSamplingDefaults.top_p),
  top_k: String(localSamplingDefaults.top_k),
  min_p: String(localSamplingDefaults.min_p),
  repeat_penalty: String(localSamplingDefaults.repeat_penalty),
};
