use crate::frame_commands::{decode_path, FrameCommandFamily, PATH_POINT_RECORD_BYTES};
use crate::prelude::*;

impl Canvas {
    pub(crate) fn polygon_packed_impl(
        &mut self,
        points: &[u8],
        contour_ends: &[u8],
        style: &Bound<'_, PyAny>,
        matrix: Matrix,
        close: bool,
    ) -> PyResult<()> {
        let (outer, contours) = decode_path(points, contour_ends)?;
        if contours.is_empty() {
            self.polygon_impl(outer, style, matrix, close)?;
        } else {
            self.complex_polygon_impl(outer, contours, style, matrix, close)?;
        }
        self.record_frame_command_ingress(
            FrameCommandFamily::Path,
            &[points, contour_ends],
            points.len() / PATH_POINT_RECORD_BYTES,
        );
        Ok(())
    }

    pub(crate) fn polygon_current_packed_impl(
        &mut self,
        points: &[u8],
        contour_ends: &[u8],
        close: bool,
    ) -> PyResult<()> {
        let (outer, contours) = decode_path(points, contour_ends)?;
        if contours.is_empty() {
            self.polygon_current_impl(outer, close)?;
        } else {
            self.complex_polygon_current_impl(outer, contours, close)?;
        }
        self.record_frame_command_ingress(
            FrameCommandFamily::Path,
            &[points, contour_ends],
            points.len() / PATH_POINT_RECORD_BYTES,
        );
        Ok(())
    }

    pub(crate) fn begin_clip_packed_impl(
        &mut self,
        points: &[u8],
        contour_ends: &[u8],
        matrix: Matrix,
    ) -> PyResult<()> {
        let (outer, contours) = decode_path(points, contour_ends)?;
        self.begin_clip_impl(outer, contours, matrix)?;
        self.record_frame_command_ingress(
            FrameCommandFamily::Path,
            &[points, contour_ends],
            points.len() / PATH_POINT_RECORD_BYTES,
        );
        self.record_frame_command_ingress(FrameCommandFamily::Barrier, &[], 1);
        Ok(())
    }
}
