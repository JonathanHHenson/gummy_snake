use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct TagId(u32);

impl TagId {
    pub const fn new(raw: u32) -> Self {
        Self(raw)
    }

    pub const fn index(self) -> usize {
        self.0 as usize
    }

    pub const fn raw(self) -> u32 {
        self.0
    }
}

#[derive(Debug, Clone, Default)]
pub struct TagRegistry {
    ids: HashMap<String, TagId>,
    names: Vec<String>,
}

impl TagRegistry {
    pub fn intern(&mut self, name: &str) -> TagId {
        if let Some(id) = self.ids.get(name) {
            return *id;
        }
        let id = TagId::new(self.names.len() as u32);
        self.names.push(name.to_string());
        self.ids.insert(name.to_string(), id);
        id
    }

    pub fn get(&self, name: &str) -> Option<TagId> {
        self.ids.get(name).copied()
    }

    pub fn name(&self, id: TagId) -> Option<&str> {
        self.names.get(id.index()).map(String::as_str)
    }
}

#[derive(Debug, Clone, Default)]
pub struct EntityTags {
    slots: Vec<Vec<TagId>>,
}

impl EntityTags {
    pub fn clear_slot(&mut self, entity_index: u32) {
        let index = entity_index as usize;
        if self.slots.len() <= index {
            self.slots.resize_with(index + 1, Vec::new);
        }
        self.slots[index].clear();
    }

    pub fn contains(&self, entity_index: u32, tag: TagId) -> bool {
        self.slots
            .get(entity_index as usize)
            .is_some_and(|tags| tags.binary_search(&tag).is_ok())
    }

    pub fn add(&mut self, entity_index: u32, tag: TagId) -> bool {
        let index = entity_index as usize;
        if self.slots.len() <= index {
            self.slots.resize_with(index + 1, Vec::new);
        }
        let tags = &mut self.slots[index];
        match tags.binary_search(&tag) {
            Ok(_) => false,
            Err(index) => {
                tags.insert(index, tag);
                true
            }
        }
    }

    pub fn remove(&mut self, entity_index: u32, tag: TagId) -> bool {
        let Some(tags) = self.slots.get_mut(entity_index as usize) else {
            return false;
        };
        let Ok(index) = tags.binary_search(&tag) else {
            return false;
        };
        tags.remove(index);
        true
    }

    pub fn tags(&self, entity_index: u32) -> &[TagId] {
        self.slots
            .get(entity_index as usize)
            .map_or(&[], Vec::as_slice)
    }
}
